"""Zeros of Polynomials presentation board.

Page: 20 x 15 in with a 1 in plain white border; the 18 x 13 in board inside holds
the title, a graph sheet with thick centre x/y axes, Degree + Number of Zeros panels
(left), Polynomial Cards + Contact Type panels (right) and a marker tray (bottom).
Curves are left off - they are made with thread and 3D-printed joints.

Run:  python3 make_zeros_board.py   (writes into print_files/)
  -> zeros_board_20x15in.pdf             vector, exact 20 x 15 in, fonts embedded
  -> zeros_board_20x15in.svg             vector, text as outlines (Illustrator/Corel/Inkscape)
  -> zeros_board_20x15in.eps             vector, for older print software
  -> zeros_board_20x15in_300dpi_CMYK.tif 6000 x 4500 px raster, CMYK
  -> zeros_board_20x15in_300dpi.png      6000 x 4500 px raster, RGB
  -> zeros_board_20x15in_300dpi.jpg      6000 x 4500 px raster, RGB
  -> zeros_board_preview.png             small preview (next to this script)
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import to_hex, to_rgb
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle
from PIL import Image

FONT_DIR = "/System/Library/Fonts/Supplemental/"
for f in ("Comic Sans MS.ttf", "Comic Sans MS Bold.ttf"):
    font_manager.fontManager.addfont(FONT_DIR + f)
plt.rcParams.update({
    "pdf.fonttype": 42,          # embed real TrueType fonts (print shops need this)
    "ps.fonttype": 42,
    "ps.papersize": "auto",      # EPS page = figure size, not Letter
    "svg.fonttype": "path",      # SVG text as outlines, no font needed
    "font.family": "Comic Sans MS",
    "font.weight": "bold",
    "mathtext.fontset": "custom",
    "mathtext.rm": "Comic Sans MS:bold",
    "mathtext.it": "Comic Sans MS:bold",
})

# ---- Page and board ----------------------------------------------------
PAGE_W, PAGE_H = 20.0, 15.0
MARGIN = 1.0                                  # plain white border, all sides
BX0, BY0 = MARGIN, MARGIN
BX1, BY1 = PAGE_W - MARGIN, PAGE_H - MARGIN   # board is 18 x 13 in
BOARD_BG = "#C7A6EE"
BOARD_EDGE = "#9C6ADE"
INK = "#1B1B2F"

# ---- Columns -----------------------------------------------------------
PAD = 0.25
COL_W = 3.7
LX = BX0 + PAD                      # left column
RX = BX1 - PAD - COL_W              # right column
CX0, CX1 = LX + COL_W + 0.25, RX - 0.25   # centre column

# ---- Graph sheet -------------------------------------------------------
SHEET = (CX0, BY0 + 1.65, CX1 - CX0, 9.35)   # x, y, w, h
UNIT = 0.65                                   # one grid unit in inches
N = 6                                         # axes run -N .. N
GRID_BG = "#FFF6E5"
MINOR_COLOR = "#E2D7F7"
MAJOR_COLORS = ["#FF3D7F", "#00B8A9", "#FFB400", "#7B2FF7", "#FF6B35"]

PINK, BLUE, GREEN, ORANGE, PURPLE = "#FF4F9A", "#2F9BFF", "#3CCB6B", "#FF8C1A", "#A45BF0"
BADGES = [PINK, BLUE, GREEN, ORANGE, PURPLE, PINK]
YELLOW_HDR = "#FFE15C"
CARD_BG = "#F4F7FF"


def blend(color, base, a):
    """Solid colour equal to `color` at opacity `a` over `base` (no PDF transparency)."""
    return to_hex([a * c + (1 - a) * b for c, b in zip(to_rgb(color), to_rgb(base))])


SHADOW = blend("#000000", BOARD_BG, 0.19)
MAJOR_SOLID = [blend(c, GRID_BG, 0.6) for c in MAJOR_COLORS]


def rbox(ax, x, y, w, h, fc, ec=None, lw=0, r=0.18, z=2, shadow=False):
    if shadow:
        ax.add_patch(FancyBboxPatch((x + 0.05, y - 0.06), w, h,
                     boxstyle=f"round,pad=0,rounding_size={r}",
                     fc=SHADOW, ec="none", zorder=z - 0.1))
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle=f"round,pad=0,rounding_size={r}",
                 fc=fc, ec=ec or "none", lw=lw, zorder=z))


def text(ax, x, y, s, size, ha="center", va="center", color=INK, z=6, **kw):
    ax.text(x, y, s, fontsize=size, ha=ha, va=va, color=color, zorder=z, **kw)


def panel(ax, x, y, w, h, outer, title, hdr_h=0.8, title_size=27):
    """Coloured panel with a yellow header tab; returns top of body area."""
    rbox(ax, x, y, w, h, outer, ec="white", lw=3, r=0.25, z=2, shadow=True)
    hx, hy = x + 0.17, y + h - hdr_h - 0.15
    rbox(ax, hx, hy, w - 0.34, hdr_h, YELLOW_HDR, r=0.2, z=3)
    text(ax, x + w / 2, hy + hdr_h / 2, title, title_size, linespacing=0.95)
    return hy - 0.14


def badge_rows(ax, x, top, w, rows, row_h, gap, num_size=27, label_size=20):
    for i, (num, label, color) in enumerate(rows):
        y = top - (i + 1) * row_h - i * gap
        rbox(ax, x, y, w, row_h, "white", r=0.14, z=3)
        rbox(ax, x + 0.07, y + 0.07, row_h - 0.14, row_h - 0.14, color, r=0.12, z=4)
        text(ax, x + row_h / 2, y + row_h / 2, num, num_size)
        text(ax, x + row_h + 0.18, y + row_h / 2, label, label_size, ha="left")


def graph_sheet(ax):
    sx, sy, sw, sh = SHEET
    cx, cy = sx + sw / 2, sy + sh / 2
    half = (N + 0.5) * UNIT
    x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half

    ax.add_patch(Rectangle((sx, sy), sw, sh, fc="white", ec="none", zorder=1))
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=GRID_BG, zorder=1.1))

    for k in range(-N, N + 1):
        if k != N:   # minor lines halfway between units
            m = (k + 0.5) * UNIT
            ax.plot([cx + m] * 2, [y0, y1], color=MINOR_COLOR, lw=1.6, zorder=1.2)
            ax.plot([x0, x1], [cy + m] * 2, color=MINOR_COLOR, lw=1.6, zorder=1.2)
        if k:
            ax.plot([cx + k * UNIT] * 2, [y0, y1], color=MAJOR_SOLID[k % 5], lw=3,
                    zorder=1.3, solid_capstyle="butt")
            ax.plot([x0, x1], [cy + k * UNIT] * 2, color=MAJOR_SOLID[(k + 2) % 5],
                    lw=3, zorder=1.3, solid_capstyle="butt")

    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                 boxstyle="round,pad=0,rounding_size=0.12",
                 fill=False, ec="#2B2D42", lw=6, zorder=1.4))

    # Thick axes with arrowheads, running into the sheet's plain border
    arrow = dict(arrowstyle="<|-|>,head_length=1.2,head_width=0.6",
                 lw=9, color=INK, shrinkA=0, shrinkB=0)
    ax.annotate("", xy=(x1 + 0.4, cy), xytext=(x0 - 0.4, cy), arrowprops=arrow, zorder=5)
    ax.annotate("", xy=(cx, y1 + 0.4), xytext=(cx, y0 - 0.4), arrowprops=arrow, zorder=5)
    text(ax, x1 + 0.22, cy + 0.38, "x", 30)
    text(ax, cx + 0.38, y1 + 0.25, "y", 30)

    lbl = dict(boxstyle="round,pad=0.1", fc=GRID_BG, ec="none")
    for k in range(-N, N + 1):
        if k:
            text(ax, cx + k * UNIT, cy - 0.27, f"{k}", 18, bbox=lbl)
            text(ax, cx - 0.17, cy + k * UNIT, f"{k}", 18, ha="right", bbox=lbl)
    text(ax, cx - 0.17, cy - 0.27, "0", 18, ha="right", bbox=lbl)


def main():
    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, PAGE_W)
    ax.set_ylim(0, PAGE_H)
    ax.axis("off")

    ax.add_patch(Rectangle((0, 0), PAGE_W, PAGE_H, fc="white", ec="none", zorder=0))
    ax.add_patch(Rectangle((BX0, BY0), BX1 - BX0, BY1 - BY0, fc=BOARD_BG,
                           ec=BOARD_EDGE, lw=12, zorder=0.5))
    top_y = BY1 - PAD

    # Title banner
    rbox(ax, CX0 + 0.3, top_y - 1.55, CX1 - CX0 - 0.6, 1.55, "#FF8DC7",
         ec="#B05CD6", lw=5, r=0.28, z=3, shadow=True)
    text(ax, (CX0 + CX1) / 2, top_y - 0.78, "Zeros of Polynomials", 56)

    graph_sheet(ax)

    # Left: Degree
    deg_h = 5.35
    top = panel(ax, LX, top_y - deg_h, COL_W, deg_h, "#B07CE8", "Degree")
    badge_rows(ax, LX + 0.17, top, COL_W - 0.34, [
        ("1", "Linear", PINK), ("2", "Quadratic", BLUE), ("3", "Cubic", GREEN),
        ("4", "Quartic", ORANGE), ("5", "Quintic", PURPLE)], 0.74, 0.09)

    # Left: Number of distinct real zeros
    zeros_h = top_y - deg_h - 0.25 - (BY0 + PAD)
    top = panel(ax, LX, BY0 + PAD, COL_W, zeros_h, "#B07CE8",
                "Number of\nDistinct Real Zeros", hdr_h=1.15, title_size=22)
    labels = ["No real zero", "One real zero", "Two real zeros",
              "Three real zeros", "Four real zeros", "Five real zeros"]
    badge_rows(ax, LX + 0.17, top, COL_W - 0.34,
               [(str(i), s, BADGES[i]) for i, s in enumerate(labels)], 0.76, 0.1,
               label_size=19)

    # Right: Polynomial cards
    cards_h = 8.2
    top = panel(ax, RX, top_y - cards_h, COL_W, cards_h, "#5B8DEF",
                "Polynomial Cards", title_size=24)
    cards = [r"$y = x + 1$", r"$y = x^2 - 4$", r"$y = x^3 - x$",
             r"$y = x^3 - 3x^2 + 2x$", r"$y = (x-1)(x+2)(x-4)$"]
    sizes = [27, 27, 27, 23, 21]
    card_h, gap = 1.22, 0.12
    for i, (c, s) in enumerate(zip(cards, sizes)):
        y = top - (i + 1) * card_h - i * gap
        rbox(ax, RX + 0.17, y, COL_W - 0.34, card_h, CARD_BG, r=0.14, z=3)
        text(ax, RX + COL_W / 2, y + card_h / 2, c, s)

    # Right: Contact type
    ct_h = top_y - cards_h - 0.25 - (BY0 + PAD)
    top = panel(ax, RX, BY0 + PAD, COL_W, ct_h, "#5B8DEF", "Contact Type",
                title_size=24)
    rbox(ax, RX + 0.17, BY0 + PAD + 0.17, COL_W - 0.34, top - (BY0 + PAD + 0.17),
         "white", r=0.14, z=3)
    for i, (label, color) in enumerate([("Cuts (Crosses)", BLUE),
                                        ("Touches", "#139A8A"),
                                        ("Does not cut", PINK)]):
        y = top - 0.55 - i * 0.95
        ax.plot([RX + 0.4, RX + 1.1], [y, y], color=color, lw=10,
                solid_capstyle="round", zorder=4)
        text(ax, RX + 1.3, y, label, 19, ha="left")

    # Bottom: marker tray + caption (under the graph sheet)
    by, bh = BY0 + PAD, 1.2
    tray_w = 3.9
    rbox(ax, CX0, by, tray_w, bh, "#E9DDFB", ec="white", lw=3, r=0.2, z=3, shadow=True)
    for i in range(6):
        mx = CX0 + 0.42 + i * 0.6
        ax.add_patch(Polygon([(mx - 0.22, by + 0.15), (mx + 0.22, by + 0.15),
                              (mx, by + 0.68)], closed=True, fc="#E8283A",
                             ec="#A3101F", lw=2, zorder=4))
    text(ax, CX0 + tray_w / 2, by + 0.95, "Zero markers", 15, color="#6C3FB5")
    cap_x = CX0 + tray_w + 0.3
    rbox(ax, cap_x, by + 0.1, CX1 - cap_x, bh - 0.2, "#BFE3FF", ec="#2F9BFF", lw=3.5,
         r=0.2, z=3, shadow=True)
    text(ax, (cap_x + CX1) / 2, by + bh / 2, "Move the markers\nto show zeros", 21,
         linespacing=1.0)

    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "print_files")
    os.makedirs(out, exist_ok=True)
    name = os.path.join(out, "zeros_board_20x15in")

    fig.savefig(name + ".pdf", metadata={"Title": "Zeros of Polynomials board, 20 x 15 in"})
    fig.savefig(name + ".svg")
    fig.savefig(name + ".eps")
    fig.savefig(name + "_300dpi.png", dpi=300)
    fig.savefig(os.path.join(here, "zeros_board_preview.png"), dpi=60)
    plt.close(fig)

    img = Image.open(name + "_300dpi.png").convert("RGB")
    img.save(name + "_300dpi.png", dpi=(300, 300), optimize=True)
    img.save(name + "_300dpi.jpg", dpi=(300, 300), quality=95, subsampling=0)
    img.convert("CMYK").save(name + "_300dpi_CMYK.tif", dpi=(300, 300),
                             compression="tiff_lzw")


if __name__ == "__main__":
    main()
