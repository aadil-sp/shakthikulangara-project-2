"""Funky presentation graph sheet: 20 x 12 in page, 1.5 in plain border, bold grid.

Run:  python3 make_graph_sheet.py   ->  graph_sheet_20x12.pdf + graph_sheet_20x12.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

PAGE_W, PAGE_H = 20.0, 12.0   # inches
BORDER = 1.5                  # plain margin on all four sides
MAJOR = 1.0                   # thick coloured line every inch
MINOR = 0.5                   # thinner line between

GRID_BG = "#FFF6E5"
MINOR_COLOR = "#D9CCF5"
FRAME_COLOR = "#2B2D42"
MAJOR_COLORS = ["#FF3D7F", "#00B8A9", "#FFB400", "#7B2FF7", "#FF6B35"]

PT = 72  # points per inch (matplotlib linewidths are in points)


def main():
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, PAGE_W)
    ax.set_ylim(0, PAGE_H)
    ax.set_aspect("equal")
    ax.axis("off")

    x0, y0 = BORDER, BORDER
    x1, y1 = PAGE_W - BORDER, PAGE_H - BORDER

    ax.add_patch(Rectangle((0, 0), PAGE_W, PAGE_H, color="white", zorder=0))
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color=GRID_BG, zorder=1))

    # Minor lines (every 0.5 in, skipping the major positions)
    n_x = round((x1 - x0) / MINOR)
    n_y = round((y1 - y0) / MINOR)
    for i in range(1, n_x):
        if i % 2:
            x = x0 + i * MINOR
            ax.plot([x, x], [y0, y1], color=MINOR_COLOR, lw=2.5, zorder=2,
                    solid_capstyle="butt")
    for j in range(1, n_y):
        if j % 2:
            y = y0 + j * MINOR
            ax.plot([x0, x1], [y, y], color=MINOR_COLOR, lw=2.5, zorder=2,
                    solid_capstyle="butt")

    # Major lines (every 1 in), cycling through the funky palette
    for k, i in enumerate(range(1, round((x1 - x0) / MAJOR))):
        x = x0 + i * MAJOR
        ax.plot([x, x], [y0, y1], color=MAJOR_COLORS[k % len(MAJOR_COLORS)],
                lw=6, zorder=3, solid_capstyle="butt", alpha=0.9)
    for k, j in enumerate(range(1, round((y1 - y0) / MAJOR))):
        y = y0 + j * MAJOR
        ax.plot([x0, x1], [y, y], color=MAJOR_COLORS[(k + 2) % len(MAJOR_COLORS)],
                lw=6, zorder=3, solid_capstyle="butt", alpha=0.9)

    # Chunky rounded frame around the grid
    frame_lw = 12
    pad = frame_lw / PT / 2
    ax.add_patch(FancyBboxPatch(
        (x0 - pad, y0 - pad), (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad,
        boxstyle="round,pad=0,rounding_size=0.25",
        fill=False, ec=FRAME_COLOR, lw=frame_lw, zorder=4))

    fig.savefig("graph_sheet_20x12.pdf")
    fig.savefig("graph_sheet_20x12.png", dpi=60)
    plt.close(fig)


if __name__ == "__main__":
    main()
