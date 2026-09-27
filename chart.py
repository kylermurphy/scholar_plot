"""Render the citations + publications chart (sized for a ~200 px sidebar).

One axes with two y-scales: citations per year as bars (left axis) and
publications per year as a line with dots (right axis). The current,
incomplete year is drawn lighter, and the subtitle says so.

Two transparent PNGs are written, one per site theme:

    figures/scholar_light.png
    figures/scholar_dark.png

They are sized to display at ~200 px wide and saved at 3x
resolution so they stay sharp on high-density screens.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

# Display size in the sidebar (CSS px) and output scale.
DISPLAY_WIDTH_PX = 200
DISPLAY_HEIGHT_PX = 150
SCALE = 3
_PX_PER_IN = 96  # CSS reference pixel

# Palettes validated for colour-vision deficiency and contrast against the
# site's light (#ffffff) and dark (#474747) backgrounds.
THEMES: dict[str, dict[str, str]] = {
    "light": {
        "citations": "#0a7fa0",
        "publications": "#d4731f",
        "ink": "#494e52",
        "muted": "#7a8288",
        "grid": "#e3e6e8",
        "halo": "#ffffff",
    },
    "dark": {
        "citations": "#2a9dbb",
        "publications": "#cf7a28",
        "ink": "#ffffff",
        "muted": "#d0d4d6",
        "grid": "#5c5c5c",
        "halo": "#474747",
    },
}

FONT_FAMILY = ["Helvetica", "Arial", "Liberation Sans", "FreeSans", "DejaVu Sans"]
FONT_SIZE = 8.0  # pt; ~10.7 CSS px at 1x


def _nice_step(raw_step: float) -> int:
    """Smallest round step (1, 1.5, 2, 2.5, 3, 4, 5 x 10^k) >= ``raw_step``."""
    raw_step = max(raw_step, 1e-9)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    for mult in (1, 1.5, 2, 2.5, 3, 4, 5, 10):
        step = mult * magnitude
        if step >= raw_step - 1e-9:
            return max(1, int(math.ceil(step)))
    return max(1, int(math.ceil(10 * magnitude)))


def _shared_scales(c_peak: float, p_peak: float) -> tuple[int, int, int, int]:
    """Pick one gridline count for both axes that wastes the least headroom.

    Returns (citations_max, citations_step, papers_max, papers_step).
    """
    best = None
    for n in (3, 4, 5):
        c_step = _nice_step(max(c_peak, 1) / n)
        p_step = _nice_step(max(p_peak, 1) / n)
        waste = (c_step * n) / max(c_peak, 1) + (p_step * n) / max(p_peak, 1)
        if best is None or waste < best[0]:
            best = (waste, c_step * n, c_step, p_step * n, p_step)
    return best[1:]


def _style_axis(ax, colors: dict[str, str]) -> None:
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(colors["muted"])
    ax.spines["bottom"].set_linewidth(0.6)
    ax.tick_params(axis="both", colors=colors["muted"], labelcolor=colors["ink"],
                   length=0, pad=2, labelsize=FONT_SIZE - 0.5)


def render_theme(data: dict[str, Any], theme: str, out_path: Path) -> Path:
    """Draw the chart for one theme and save it as a transparent PNG."""
    colors = THEMES[theme]
    rows = data["per_year"]
    partial = data.get("partial_year")

    years = [r["year"] for r in rows]
    cites = [r["citations"] for r in rows]
    pubs = [r["publications"] for r in rows]

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": FONT_FAMILY,
        "font.size": FONT_SIZE,
    })

    fig = plt.figure(
        figsize=(DISPLAY_WIDTH_PX / _PX_PER_IN, DISPLAY_HEIGHT_PX / _PX_PER_IN),
        dpi=_PX_PER_IN * SCALE,
    )
    fig.patch.set_alpha(0)
    ax = fig.add_axes((0.14, 0.13, 0.74, 0.62))
    ax.patch.set_alpha(0)

    # Shared gridlines: both axes get the same number of round-numbered steps.
    c_max, c_step, p_max, p_step = _shared_scales(max(cites or [0]), max(pubs or [0]))

    # Citations: bars on the left axis, current year lighter.
    bar_colors = [colors["citations"]] * len(years)
    alphas = [1.0 if y != partial else 0.4 for y in years]
    bars = ax.bar(years, cites, width=0.72, color=bar_colors, linewidth=0, zorder=2)
    for bar, a in zip(bars, alphas):
        bar.set_alpha(a)

    ax.set_ylim(0, c_max)
    ax.set_yticks(range(0, c_max + 1, c_step))
    ax.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda v, _: f"{int(v):,}" if v < 10_000 else f"{v/1000:.0f}k"))
    ax.grid(axis="y", color=colors["grid"], linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    _style_axis(ax, colors)

    # Publications: line + dots on the right axis, current year hollow.
    ax2 = ax.twinx()
    ax2.patch.set_alpha(0)
    full = [(y, p) for y, p in zip(years, pubs) if y != partial]
    ax2.plot([y for y, _ in full], [p for _, p in full], color=colors["publications"],
             linewidth=1.1, zorder=4, solid_capstyle="round")
    ax2.scatter([y for y, _ in full], [p for _, p in full], s=9, color=colors["publications"],
                edgecolors=colors["halo"], linewidths=0.5, zorder=5)
    if partial in years:
        i = years.index(partial)
        if full:
            ax2.plot([full[-1][0], partial], [full[-1][1], pubs[i]], color=colors["publications"],
                     linewidth=1.0, linestyle=(0, (1.5, 1.2)), zorder=4)
        ax2.scatter([partial], [pubs[i]], s=9, facecolors=colors["halo"],
                    edgecolors=colors["publications"], linewidths=0.9, zorder=5)
    ax2.set_ylim(0, p_max)
    ax2.set_yticks(range(0, p_max + 1, p_step))
    _style_axis(ax2, colors)
    ax2.spines["bottom"].set_visible(False)

    # X axis: every 5th year.
    if years:
        first, last = years[0], years[-1]
        ax.set_xlim(first - 0.7, last + 0.7)
        ticks = [y for y in range(first, last + 1) if y % 5 == 0]
        ax.set_xticks(ticks)
        ax.set_xticklabels([str(t) for t in ticks])

    # Legend (ink text, coloured marks) and axis titles above the plot.
    handles = [
        Patch(facecolor=colors["citations"], edgecolor="none", label="Citations"),
        Line2D([0], [0], color=colors["publications"], linewidth=1.1, marker="o",
               markersize=3, markeredgecolor=colors["halo"], markeredgewidth=0.5,
               label="Papers"),
    ]
    leg = fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.12, 1.0), ncol=2,
                     frameon=False, fontsize=FONT_SIZE, handlelength=1.3, handleheight=0.7,
                     columnspacing=1.0, handletextpad=0.4, borderaxespad=0.2)
    for text in leg.get_texts():
        text.set_color(colors["ink"])
    note = "per year" + (f" \u00b7 {partial} to date" if partial in years else "")
    fig.text(0.14, 0.79, note, fontsize=FONT_SIZE - 1.0, color=colors["muted"],
             ha="left", va="bottom")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, transparent=True)
    plt.close(fig)
    return out_path


def render(data: dict[str, Any], out_dir: Path) -> list[Path]:
    """Render light and dark PNGs into ``out_dir/figures`` and return their paths."""
    out_dir = Path(out_dir)
    return [
        render_theme(data, theme, out_dir / "figures" / f"scholar_{theme}.png")
        for theme in ("light", "dark")
    ]
