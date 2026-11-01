"""Static chart images for the PowerPoint decks.

Native PowerPoint charts render as empty boxes in many phone and messaging previewers (iOS Quick Look,
WhatsApp, some mail/Drive previews). Decks therefore embed these high-resolution PNGs so every slide
displays everywhere; the Excel workbooks keep live, editable charts.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

MAROON, GOLD, TEAL, SAFFRON, INDIGO = "#7A1E2C", "#D99A2B", "#1F8A86", "#D2622A", "#4A5FB0"
INK, MUTED, GRID, PALE = "#2B2D42", "#6B7280", "#E5E1DC", "#C9B9A8"
DPI = 220

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.7,
    "axes.axisbelow": True, "legend.frameon": False, "legend.fontsize": 9, "axes.titlesize": 11,
    "axes.titlecolor": INK, "axes.titleweight": "bold", "figure.facecolor": "white", "axes.facecolor": "white",
})


def _indian(v: float, _pos=None) -> str:
    """1,23,456 style grouping (Indian numbering)."""
    neg = v < 0
    s = f"{abs(int(round(v))):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if neg else "") + s


FMT = FuncFormatter(_indian)


def _fig(w: float, h: float):
    fig, ax = plt.subplots(figsize=(w, h), dpi=DPI)
    return fig, ax


def _save(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(pad=0.6)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return str(path)


def _thin_labels(ax, labels, every: int, rotate: int = 0):
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([lab if i % every == 0 else "" for i, lab in enumerate(labels)], rotation=rotate,
                       ha="right" if rotate else "center")


def bars(path, labels, series, *, w=6.3, h=3.85, stacked=False, horizontal=False, values=False, title=None,
         colors=None, value_fmt=None, every=1, rotate=0, ylim=None, legend=True, highlight=None):
    """series: list of (name, values). highlight: {index: colour} to colour individual bars (single series)."""
    fig, ax = _fig(w, h)
    colors = colors or [MAROON, GOLD, TEAL, INDIGO, SAFFRON]
    n = len(labels)
    xs = list(range(n))
    width = 0.8 if stacked or len(series) == 1 else 0.8 / len(series)
    bottom = [0.0] * n
    for k, (name, vals) in enumerate(series):
        vals = [0 if v is None else v for v in vals]
        col = colors[k % len(colors)]
        cols = [highlight.get(i, col) for i in range(n)] if highlight and len(series) == 1 else col
        if horizontal:
            pos = [x + (0 if stacked or len(series) == 1 else (k - (len(series) - 1) / 2) * width) for x in xs]
            bs = ax.barh(pos, vals, height=width, left=bottom if stacked else None, color=cols, label=name)
        else:
            pos = [x + (0 if stacked or len(series) == 1 else (k - (len(series) - 1) / 2) * width) for x in xs]
            bs = ax.bar(pos, vals, width=width, bottom=bottom if stacked else None, color=cols, label=name,
                        edgecolor="white" if stacked else None, linewidth=0.8 if stacked else 0)
        if values:
            for b, v in zip(bs, vals):
                txt = value_fmt(v) if value_fmt else _indian(v)
                if horizontal:
                    ax.text(b.get_width() + (max(vals) * 0.01 if vals else 0), b.get_y() + b.get_height() / 2, txt,
                            va="center", fontsize=8.5, color=INK)
                else:
                    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + (b.get_y() if stacked else 0), txt,
                            ha="center", va="bottom", fontsize=8.5, color=INK)
        if stacked:
            bottom = [a + b for a, b in zip(bottom, vals)]
    if horizontal:
        ax.set_yticks(xs)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.grid(axis="x")
        ax.grid(axis="y", visible=False)
        ax.xaxis.set_major_formatter(FMT if not value_fmt else FuncFormatter(lambda v, _: value_fmt(v)))
        if ylim:
            ax.set_xlim(*ylim)
    else:
        _thin_labels(ax, labels, every, rotate)
        ax.yaxis.set_major_formatter(FMT if not value_fmt else FuncFormatter(lambda v, _: value_fmt(v)))
        if ylim:
            ax.set_ylim(*ylim)
    ax.tick_params(length=0)
    if title:
        ax.set_title(title, loc="left")
    if legend and len(series) > 1:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1 if not rotate else -0.22), ncol=len(series))
    return _save(fig, Path(path))


def lines(path, labels, series, *, w=6.3, h=3.85, every=12, title=None, colors=None, dashed=(), band=None,
          ymin=0, markers=False, rotate=0):
    """band: (low_values, high_values, colour) shaded region."""
    fig, ax = _fig(w, h)
    colors = colors or [MAROON, GOLD, TEAL, INDIGO]
    xs = list(range(len(labels)))
    if band:
        lo, hi, col = band
        pts = [(x, a, b) for x, a, b in zip(xs, lo, hi) if a is not None and b is not None]
        if pts:
            ax.fill_between([p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts], color=col, alpha=0.18,
                            linewidth=0, label="80% range")
    for k, (name, vals) in enumerate(series):
        ys = [float("nan") if v is None else v for v in vals]
        ax.plot(xs, ys, color=colors[k % len(colors)], linewidth=2.0, label=name,
                linestyle="--" if name in dashed else "-", marker="o" if markers else None, markersize=3.5)
    _thin_labels(ax, labels, every, rotate)
    ax.set_xlim(-0.4, len(labels) - 0.6)
    ax.tick_params(axis="x", pad=6)
    ax.yaxis.set_major_formatter(FMT)
    if ymin is not None:
        ax.set_ylim(bottom=ymin)
    ax.tick_params(length=0)
    if title:
        ax.set_title(title, loc="left")
    if len(series) > 1 or band:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1 if not rotate else -0.22), ncol=len(series) + (1 if band else 0))
    return _save(fig, Path(path))


def donut(path, labels, values, *, w=3.0, h=3.6, title=None, colors=None):
    fig, ax = _fig(w, h)
    colors = colors or [MAROON, GOLD, TEAL, INDIGO, SAFFRON]
    total = sum(values) or 1
    wedges, _ = ax.pie(values, colors=colors[:len(values)], startangle=90, counterclock=False,
                       wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 2})
    ax.set_aspect("equal")
    ax.legend(wedges, [f"{lab} {100 * v / total:.0f}%" for lab, v in zip(labels, values)], loc="upper center",
              bbox_to_anchor=(0.5, 0.02), ncol=1 if len(labels) > 3 else len(labels), fontsize=9)
    if title:
        ax.set_title(title, loc="center")
    ax.grid(False)
    return _save(fig, Path(path))
