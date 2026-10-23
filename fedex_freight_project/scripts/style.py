"""House style for report figures: one palette, thin marks, hairline grid, no dual axes."""
import matplotlib
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
# categorical slots in fixed order (validated palette, light mode)
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, VIOLET, RED = (
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
NEUTRAL = "#9a9893"
# diverging poles (cool = good/above, warm = bad/below) with a gray midpoint
POS, NEG = BLUE, ORANGE


def apply():
    matplotlib.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK, "text.color": INK,
        "xtick.color": INK_2, "ytick.color": INK_2, "axes.grid": True, "axes.axisbelow": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.labelsize": 9, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "legend.fontsize": 8.5, "legend.frameon": False, "lines.linewidth": 2.0, "font.family": "DejaVu Sans",
        "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight",
    })


def subtitle(ax, text):
    """Grey one-line subtitle under the bold left-aligned title."""
    ax.text(0, 1.015, text, transform=ax.transAxes, fontsize=8.5, color=INK_2, va="bottom")


def source(fig, text):
    fig.text(0.01, -0.07, "Source: " + text, fontsize=7, color=INK_2, ha="left", va="top")


def save(fig, path):
    fig.savefig(path)
    plt.close(fig)
