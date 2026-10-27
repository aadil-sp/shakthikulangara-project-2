"""Builds the exhibition charts: two A2 posters per project.

    python3 reports/build_charts.py          (run build_reports.py first: it makes the graphs)

Chart 1 of each project explains the problem, the idea and the parts.
Chart 2 explains how it works and what the tests showed.
Output: reports/charts/*.pdf (vector, prints sharp on A2, A3 or chart paper size).
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, Image, KeepInFrame, Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.frames import Frame

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = HERE / "charts"
OUT.mkdir(exist_ok=True)

W, H = 420 * mm, 594 * mm      # A2 portrait
M = 16 * mm                    # outer margin
GAP = 9 * mm
HEADER_H = 88 * mm


# =============================================================================
# Styles
# =============================================================================
def st(theme):
    return {
        "body": ParagraphStyle("b", fontName="Helvetica", fontSize=25, leading=33, textColor=colors.HexColor("#1f2937")),
        "big": ParagraphStyle("g", fontName="Helvetica", fontSize=27, leading=36, textColor=colors.HexColor("#1f2937")),
        "bullet": ParagraphStyle("u", fontName="Helvetica", fontSize=26, leading=34, leftIndent=30, bulletIndent=2,
                                 bulletFontSize=20, textColor=colors.HexColor("#1f2937"), spaceAfter=10),
        "cap": ParagraphStyle("c", fontName="Helvetica-Oblique", fontSize=18, leading=23, alignment=TA_CENTER,
                              textColor=colors.HexColor("#64748b")),
        "cell": ParagraphStyle("cl", fontName="Helvetica", fontSize=22, leading=27, textColor=colors.HexColor("#1f2937")),
        "cellb": ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=colors.white),
        "cells": ParagraphStyle("cs", fontName="Helvetica", fontSize=19, leading=22, textColor=colors.HexColor("#1f2937")),
        "cellbs": ParagraphStyle("cbs", fontName="Helvetica-Bold", fontSize=19, leading=22, textColor=colors.white),
        "quote": ParagraphStyle("q", fontName="Helvetica-Bold", fontSize=22, leading=29, alignment=TA_CENTER,
                                textColor=colors.HexColor(theme)),
    }


def bullets(items, s):
    return [Paragraph(t, s["bullet"], bulletText="●") for t in items]


class FitTable(Flowable):
    """A table that shrinks its columns to fit the box. A fresh Table is built on every
    measurement, because reportlab caches row heights from the first wrap."""
    def __init__(self, data, widths, style):
        super().__init__()
        self.data, self.widths, self.style = data, widths, style

    def wrap(self, aw, ah):
        f = min(1.0, aw / sum(self.widths))                  # never stretch past the design width
        self.t = Table(self.data, colWidths=[w * f for w in self.widths])
        self.t.setStyle(self.style)
        self.width, self.height = self.t.wrap(aw, ah)
        return self.width, self.height

    def draw(self):
        self.t.drawOn(self.canv, 0, 0)


def table(rows, widths_mm, s, theme, zebra="#f8fafc", compact=False):
    cell, cellb = (s["cells"], s["cellbs"]) if compact else (s["cell"], s["cellb"])
    data = [[Paragraph(str(c), cellb if r == 0 else cell) for c in row] for r, row in enumerate(rows)]
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(zebra)]),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4 if compact else 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if compact else 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ])
    return FitTable(data, [w * mm * 1.6 for w in widths_mm], style)


def img(path, width_mm, s=None, caption=None):
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(str(path)).getSize()
    w = width_mm * mm
    out = [Image(str(path), width=w, height=w * ih / iw)]
    if caption and s:
        out += [Spacer(1, 3), Paragraph(caption, s["cap"])]
    return out


# =============================================================================
# Hand-drawn style pictures (vector)
# =============================================================================
class Drawing(Flowable):
    def __init__(self, w_mm, h_mm, fn):
        super().__init__()
        self.width, self.height, self.fn = w_mm * mm, h_mm * mm, fn

    def draw(self):
        self.fn(self.canv, self.width, self.height)


def label(c, x, y, text, size=13, color="#1f2937", bold=True, anchor="c"):
    c.setFillColor(colors.HexColor(color))
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    {"c": c.drawCentredString, "l": c.drawString, "r": c.drawRightString}[anchor](x, y, text)


def fish(c, x, y, s=1.0, color="#64748b"):
    c.setFillColor(colors.HexColor(color))
    c.setStrokeColor(colors.HexColor("#334155"))
    c.setLineWidth(0.8)
    c.ellipse(x - 16 * s, y - 6 * s, x + 12 * s, y + 6 * s, fill=1, stroke=1)
    p = c.beginPath()
    p.moveTo(x + 10 * s, y); p.lineTo(x + 20 * s, y + 7 * s); p.lineTo(x + 20 * s, y - 7 * s); p.close()
    c.drawPath(p, fill=1, stroke=1)
    c.setFillColor(colors.white)
    c.circle(x - 10 * s, y + 1.5 * s, 1.6 * s, fill=1, stroke=0)


def draw_fish_hold(c, w, h):
    """Cross-section of the insulated fish hold with the sensors in place."""
    import random
    x0, y0 = 70 * mm, 14 * mm
    bw, bh = w - 140 * mm, h - 30 * mm
    water_h = 14 * mm
    c.setLineWidth(5); c.setStrokeColor(colors.HexColor("#0f3d4c")); c.setFillColor(colors.HexColor("#f1f5f9"))
    c.roundRect(x0, y0, bw, bh, 10, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#0f3d4c")); c.rect(x0 - 8, y0 + bh - 2, bw + 16, 12, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#93c5fd")); c.rect(x0 + 3, y0 + 3, bw - 6, water_h, fill=1, stroke=0)
    ice_top = y0 + bh - 26 * mm
    c.setFillColor(colors.HexColor("#e0f2fe")); c.rect(x0 + 3, y0 + water_h + 3, bw - 6, ice_top - y0 - water_h - 3, fill=1, stroke=0)
    rng = random.Random(4)
    c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor("#bae6fd")); c.setLineWidth(0.8)
    for _ in range(110):
        c.rect(x0 + 8 + rng.random() * (bw - 20), y0 + water_h + 6 + rng.random() * (ice_top - y0 - water_h - 14), 6, 6, fill=1, stroke=1)
    for row in range(3):
        for k in range(6):
            fish(c, x0 + 22 * mm + k * (bw - 44 * mm) / 5 + (row % 2) * 7 * mm, y0 + water_h + 12 * mm + row * 13 * mm, 1.7,
                 ["#64748b", "#94a3b8", "#78716c"][(row + k) % 3])
    c.setFillColor(colors.HexColor("#0f3d4c")); c.rect(x0 + bw - 2, y0 + 4, 18 * mm, 9, fill=1, stroke=0)
    label(c, x0 + bw + 9 * mm, y0 - 9 * mm, "drain outlet", 17, "#0f3d4c")
    sx = x0 + 28 * mm
    c.setFillColor(colors.HexColor("#2563eb")); c.roundRect(sx - 17 * mm, y0 + bh - 14 * mm, 34 * mm, 11 * mm, 3, fill=1, stroke=0)
    label(c, sx, y0 + bh - 10.5 * mm, "HC-SR04", 17, "#ffffff")
    c.setStrokeColor(colors.HexColor("#2563eb")); c.setDash(5, 5); c.setLineWidth(2.5)
    c.line(sx, y0 + bh - 15 * mm, sx, y0 + water_h + 3); c.setDash()
    for k, (name, col) in enumerate((("MQ-135", "#7c3aed"), ("MQ-4", "#dc2626"))):
        gx = x0 + bw / 2 + 10 * mm + k * 36 * mm
        c.setFillColor(colors.HexColor(col)); c.roundRect(gx - 15 * mm, y0 + bh - 15 * mm, 30 * mm, 11 * mm, 5, fill=1, stroke=0)
        label(c, gx, y0 + bh - 11.5 * mm, name, 17, "#ffffff")
    dx, dy = x0 + bw / 2 - 8 * mm, y0 + water_h + 31 * mm
    c.setFillColor(colors.HexColor("#ea580c")); c.roundRect(dx - 14 * mm, dy, 28 * mm, 10 * mm, 3, fill=1, stroke=0)
    label(c, dx, dy + 3.2 * mm, "DHT11", 17, "#ffffff")
    c.setStrokeColor(colors.HexColor("#475569")); c.setLineWidth(1.5)
    label(c, 4 * mm, y0 + bh - 6 * mm, "Ultrasonic measures", 19, "#2563eb", anchor="l")
    label(c, 4 * mm, y0 + bh - 14 * mm, "the meltwater height", 19, "#2563eb", anchor="l")
    label(c, 4 * mm, y0 + water_h + 4 * mm, "Meltwater: must", 19, "#1d4ed8", anchor="l")
    label(c, 4 * mm, y0 + water_h - 4 * mm, "drain away", 19, "#1d4ed8", anchor="l")
    rx = x0 + bw + 8 * mm
    label(c, rx, y0 + bh - 6 * mm, "Gas sensors smell", 19, "#7c3aed", anchor="l")
    label(c, rx, y0 + bh - 14 * mm, "the air over the fish", 19, "#7c3aed", anchor="l")
    label(c, rx, dy + 8 * mm, "DHT11 sits in the", 19, "#ea580c", anchor="l")
    label(c, rx, dy, "ice: should be 0 \u00b0C", 19, "#ea580c", anchor="l")


def draw_traffic_light(c, w, h):
    """The three status LEDs and what each one means."""
    cx = 32 * mm
    c.setFillColor(colors.HexColor("#1f2937")); c.roundRect(cx - 20 * mm, 6 * mm, 40 * mm, h - 12 * mm, 14, fill=1, stroke=0)
    lights = [("#dc2626", "RED strobe", "DANGER - act now", "gas leak, vapour, fire or flooding"),
              ("#eab308", "YELLOW blink", "WARNING - check", "a reading is rising"),
              ("#16a34a", "GREEN steady", "SAFE", "all sensors normal")]
    step = (h - 24 * mm) / 3
    for i, (col, name, meaning, why) in enumerate(lights):
        y = h - 12 * mm - step * (i + 0.5)
        c.setFillColor(colors.HexColor(col)); c.circle(cx, y, 13 * mm, fill=1, stroke=0)
        c.setFillColor(colors.Color(1, 1, 1, alpha=0.35)); c.circle(cx - 4 * mm, y + 4 * mm, 4 * mm, fill=1, stroke=0)
        label(c, cx + 25 * mm, y + 5 * mm, name, 26, col, anchor="l")
        label(c, cx + 25 * mm, y - 4 * mm, meaning, 21, "#1f2937", anchor="l")
        label(c, cx + 25 * mm, y - 12 * mm, why, 16, "#64748b", bold=False, anchor="l")


def draw_ceiling_camera(c, w, h):
    """The ceiling camera looking down at the car and the goal marker."""
    cx = w / 2
    # ceiling + camera
    c.setFillColor(colors.HexColor("#cbd5e1")); c.rect(0, h - 8 * mm, w, 8 * mm, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1e293b")); c.roundRect(cx - 14 * mm, h - 24 * mm, 28 * mm, 14 * mm, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#60a5fa")); c.circle(cx, h - 24 * mm, 5 * mm, fill=1, stroke=0)
    label(c, cx + 20 * mm, h - 19 * mm, "USB camera on the ceiling", 18.8, "#1e293b", anchor="l")
    # view cone
    floor_y = 22 * mm
    c.setFillColor(colors.Color(0.38, 0.65, 0.98, alpha=0.18)); c.setStrokeColor(colors.HexColor("#60a5fa")); c.setLineWidth(1.5)
    p = c.beginPath(); p.moveTo(cx, h - 26 * mm); p.lineTo(18 * mm, floor_y); p.lineTo(w - 18 * mm, floor_y); p.close()
    c.drawPath(p, fill=1, stroke=1)
    # floor
    c.setFillColor(colors.HexColor("#d6d3d1")); c.rect(8 * mm, floor_y - 8 * mm, w - 16 * mm, 8 * mm, fill=1, stroke=0)
    # car with marker
    carx = 40 * mm
    c.setFillColor(colors.HexColor("#1d4ed8")); c.roundRect(carx - 18 * mm, floor_y, 36 * mm, 13 * mm, 4, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#111827"))
    c.circle(carx - 11 * mm, floor_y, 5 * mm, fill=1, stroke=0); c.circle(carx + 11 * mm, floor_y, 5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.rect(carx - 7 * mm, floor_y + 13 * mm, 14 * mm, 3 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black); c.rect(carx - 6 * mm, floor_y + 13.6 * mm, 4 * mm, 1.8 * mm, fill=1, stroke=0)
    c.rect(carx + 1 * mm, floor_y + 13.6 * mm, 3 * mm, 1.8 * mm, fill=1, stroke=0)
    label(c, carx, floor_y + 20 * mm, "car marker (ID 0)", 17.4, "#1d4ed8")
    # goal
    gx = w - 45 * mm
    c.setFillColor(colors.white); c.rect(gx - 9 * mm, floor_y, 18 * mm, 2.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black); c.rect(gx - 7 * mm, floor_y + 0.5 * mm, 5 * mm, 1.5 * mm, fill=1, stroke=0)
    label(c, gx, floor_y + 7 * mm, "goal marker", 17.4, "#15803d")
    # path
    c.setStrokeColor(colors.HexColor("#16a34a")); c.setDash(6, 5); c.setLineWidth(3)
    c.bezier(carx + 20 * mm, floor_y + 6 * mm, cx - 10 * mm, floor_y + 30 * mm, cx + 30 * mm, floor_y + 22 * mm, gx - 10 * mm, floor_y + 4 * mm)
    c.setDash()
    label(c, cx, floor_y - 15 * mm, "the car drives itself to the goal or to any point clicked on the screen", 18.8, "#374151", bold=False)


class Steps(Flowable):
    """The program flow as big numbered boxes with arrows. Steps starting with '?' are decisions."""
    BOX, GAP = 15 * mm, 6 * mm

    def __init__(self, steps, theme):
        super().__init__()
        self.steps, self.theme = steps, theme

    def wrap(self, aw, ah):
        n = len(self.steps)
        self.BOX = min(18 * mm, ah / (n + 0.25 * (n - 1)))     # steps grow or shrink to fill the box height
        self.GAP = 0.25 * self.BOX
        self.width = aw
        self.height = n * self.BOX + (n - 1) * self.GAP
        return self.width, self.height

    def draw(self):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        c, w = self.canv, self.width
        for i, t in enumerate(self.steps):
            decision = t.startswith("?")
            text = t.lstrip("? ")
            y = self.height - (i + 1) * self.BOX - i * self.GAP
            c.setLineWidth(2.5)
            c.setStrokeColor(colors.HexColor(self.theme))
            c.setFillColor(colors.HexColor("#fef9c3") if decision else colors.white)
            c.roundRect(0, y, w, self.BOX, 7 if not decision else 2, fill=1, stroke=1)
            c.setFillColor(colors.HexColor(self.theme))
            r = self.BOX * 0.36
            c.circle(r + 3 * mm, y + self.BOX / 2, r, fill=1, stroke=0)
            label(c, r + 3 * mm, y + self.BOX / 2 - r * 0.45, str(i + 1), r * 1.3, "#ffffff")
            size = min(26, self.BOX / mm * 1.9)
            tx = 2 * r + 7 * mm
            while stringWidth(text, "Helvetica", size) > w - tx - 3 * mm and size > 11:
                size -= 0.5
            label(c, tx, y + self.BOX / 2 - size / 3, text, size, "#1f2937", bold=False, anchor="l")
            if i < len(self.steps) - 1:
                cx = w / 2
                c.setFillColor(colors.HexColor(self.theme))
                p = c.beginPath(); p.moveTo(cx - 7, y - 1); p.lineTo(cx + 7, y - 1); p.lineTo(cx, y - self.GAP + 2); p.close()
                c.drawPath(p, fill=1, stroke=0)


def blocks(inputs, center, outputs, theme, w_mm=360, h_mm=112):
    """Inputs -> brain -> outputs, drawn big enough to read from a few steps away."""
    def fn(c, w, h):
        bw, bh = 108 * mm, 15 * mm
        cw, ch = 92 * mm, min(h - 10 * mm, 70 * mm)
        cx0, cy0 = (w - cw) / 2, (h - ch) / 2
        def column(items, x, fill, edge):
            n = len(items)
            gap = (h - n * bh) / (n + 1)
            ys = []
            for i, t in enumerate(items):
                y = h - gap * (i + 1) - bh * (i + 1)
                c.setFillColor(colors.HexColor(fill)); c.setStrokeColor(colors.HexColor(edge)); c.setLineWidth(2)
                c.roundRect(x, y, bw, bh, 8, fill=1, stroke=1)
                label(c, x + bw / 2, y + bh / 2 - 6, t, 19, "#1f2937")
                ys.append(y + bh / 2)
            return ys
        lys = column(inputs, 0, "#ffffff", "#94a3b8")
        rys = column(outputs, w - bw, "#ffffff", "#94a3b8")
        c.setStrokeColor(colors.HexColor(theme)); c.setLineWidth(3); c.setFillColor(colors.HexColor(theme))
        for y in lys:
            c.line(bw, y, cx0 - 4, cy0 + ch / 2)
        for y in rys:
            c.line(cx0 + cw + 4, cy0 + ch / 2, w - bw - 6, y)
            p = c.beginPath(); p.moveTo(w - bw, y); p.lineTo(w - bw - 12, y + 6); p.lineTo(w - bw - 12, y - 6); p.close()
            c.drawPath(p, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(theme))
        c.roundRect(cx0, cy0, cw, ch, 14, fill=1, stroke=0)
        lines = center.split("\n")
        for i, t in enumerate(lines):
            label(c, w / 2, cy0 + ch / 2 + (len(lines) / 2 - i - 0.8) * 30, t, 27 if i == 0 else 19, "#ffffff")
        label(c, bw / 2, 2, "SENSORS (inputs)", 15, "#64748b")
        label(c, w - bw / 2, 2, "OUTPUTS", 15, "#64748b")
    return Drawing(w_mm, h_mm, fn)


# =============================================================================
# Poster frame
# =============================================================================
def header(c, p):
    theme = colors.HexColor(p["theme"])
    c.setFillColor(theme)
    c.roundRect(M, H - M - HEADER_H, W - 2 * M, HEADER_H, 18, fill=1, stroke=0)
    c.setFillColor(colors.HexColor(p["theme2"]))
    c.roundRect(M, H - M - HEADER_H, W - 2 * M, 18 * mm, 18, fill=1, stroke=0)
    c.rect(M, H - M - HEADER_H + 9 * mm, W - 2 * M, 9 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(M + 14 * mm, H - M - 16 * mm, p["category"].upper() + "  ·  CHART " + p["n"])
    c.drawRightString(W - M - 14 * mm, H - M - 16 * mm, p["board"])
    c.setFont("Helvetica-Bold", 64)
    c.drawString(M + 14 * mm, H - M - 44 * mm, p["title"])
    c.setFont("Helvetica", 26)
    c.drawString(M + 14 * mm, H - M - 60 * mm, p["subtitle"])
    c.setFont("Helvetica-Bold", 22)
    c.drawString(M + 14 * mm, H - M - HEADER_H + 5.5 * mm, p["tagline"])


def box(c, x, y, w, h, num, title, flow, theme, tint):
    c.setFillColor(colors.HexColor(tint))
    c.setStrokeColor(colors.HexColor(theme))
    c.setLineWidth(3)
    c.roundRect(x, y, w, h, 14, fill=1, stroke=1)
    # number badge + title
    c.setFillColor(colors.HexColor(theme))
    c.circle(x + 15 * mm, y + h - 13 * mm, 8.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(x + 15 * mm, y + h - 16.3 * mm, str(num))
    c.setFillColor(colors.HexColor(theme))
    c.setFont("Helvetica-Bold", 28)
    c.drawString(x + 28 * mm, y + h - 16 * mm, title)
    aw, ah = w - 16 * mm, h - 33 * mm
    inner = KeepInFrame(aw, ah, flow, mode="shrink", hAlign="CENTER")
    inner.canv = c
    iw, ih = inner.wrap(aw, ah)
    inner.drawOn(c, x + 8 * mm + (aw - iw) / 2, y + 6 * mm + (ah - ih) / 2)   # centred in the box


def poster(path, p, layout):
    """layout: list of rows; each row = (height_mm, [(width_fraction, title, flowables), ...])."""
    c = canvas.Canvas(str(path), pagesize=(W, H))
    c.setTitle(f"{p['title']} - chart {p['n']}")
    c.setFillColor(colors.HexColor(p["paper"]))
    c.rect(0, 0, W, H, fill=1, stroke=0)
    header(c, p)
    y = H - M - HEADER_H - GAP
    avail = y - 14 * mm - GAP * (len(layout) - 1)          # leave room for the footer line
    scale = avail / sum(r[0] * mm for r in layout)          # rows share the page in proportion
    num = 1
    total_w = W - 2 * M
    for row_h, cells in layout:
        h = row_h * mm * scale
        x = M
        free = total_w - GAP * (len(cells) - 1)
        for frac, title, flow in cells:
            w = free * frac
            box(c, x, y - h, w, h, num, title, flow, p["theme"], p["tint"])
            num += 1
            x += w + GAP
        y -= h + GAP
    c.setFont("Helvetica", 13)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(W / 2, 8 * mm, p["footer"])
    c.save()
    print("  wrote", path.relative_to(HERE.parent))


# =============================================================================
# Electronics: HazardGuard C3
# =============================================================================
def electronics():
    base = dict(title="HazardGuard C3", theme="#c2410c", theme2="#9a3412", tint="#fff7ed", paper="#fffbf5",
                category="Electronics", board="ESP32-C3", footer="HazardGuard C3 - multi-hazard alarm with a phone dashboard")
    s = st(base["theme"])
    hazards = table([["Danger", "Sensor", "How it is noticed"],
                     ["LPG / gas leak", "MQ-5", "gas level rises above the limit"],
                     ["Alcohol / solvent vapour", "MQ-3", "vapour level rises"],
                     ["Overheating / fire", "DHT11", "temperature above 40 / 52 °C"],
                     ["Water leak / flooding", "Soil probe", "floor gets wet"]], [62, 32, 80], s, base["theme"])
    parts = table([["Part", "Job", "Rs."],
                   ["ESP32-C3 SuperMini", "brain + WiFi hotspot", "300"],
                   ["MQ-5 gas sensor", "LPG / natural gas", "150"],
                   ["MQ-3 gas sensor", "alcohol, solvents", "150"],
                   ["DHT11", "temperature, humidity", "110"],
                   ["Soil moisture probe", "water on the floor", "80"],
                   ["3 LEDs + 220 Ω", "green / yellow / red", "15"],
                   ["5 V USB adapter", "power", "150"],
                   ["Total", "", "955"]], [50, 50, 18], s, base["theme"], compact=True)
    poster(OUT / "Electronics_Chart_1_The_Idea.pdf", dict(base, n="1",
        subtitle="One small board that watches four dangers at home or at work",
        tagline="Gas · Vapour · Heat · Water  →  Green · Yellow · Red  +  your phone"), [
        (100, [(0.5, "The problem", bullets([
            "LPG leaks, kitchen fires and burst pipes cause accidents every year.",
            "Most cheap alarms watch only <b>one</b> danger.",
            "You cannot check them from another room.",
            "Unplug a sensor and they still say 'all clear'."], s)),
               (0.5, "Our idea", bullets([
            "One ESP32-C3 watches <b>four</b> dangers at once.",
            "Three LEDs work like a <b>traffic light</b>.",
            "Its own WiFi: any phone opens a live dashboard.",
            "It tells you when a sensor is missing."], s))]),
        (108, [(1.0, "Four dangers, one board", [hazards])]),
        (130, [(0.45, "Traffic-light warning", [Drawing(150, 112, draw_traffic_light)]),
               (0.55, "Parts we used", [parts])]),
        (125, [(1.0, "How the parts connect", [blocks(["MQ-5  LPG / gas", "MQ-3  alcohol", "DHT11  heat", "Soil probe  water"],
            "ESP32-C3\ncompares with limits\n+ WiFi hotspot", ["Green LED  safe", "Yellow LED  warning", "Red LED  danger", "Phone  192.168.4.1"], base["theme"])])]),
    ])
    wiring = table([["Part", "ESP32-C3 pin", "Power"],
                    ["MQ-5 AO", "GPIO 1", "5 V"], ["MQ-3 AO", "GPIO 4", "5 V"], ["Soil probe AO", "GPIO 0", "3.3 V"],
                    ["DHT11 DATA", "GPIO 6", "3.3 V"], ["Green LED", "GPIO 7", "220 Ω to GND"],
                    ["Yellow LED", "GPIO 8", "220 Ω to GND"], ["Red LED", "GPIO 3", "220 Ω to GND"]], [40, 34, 40], s, base["theme"], compact=True)
    tests = table([["We did", "It showed"],
                   ["Unlit gas lighter at MQ-5", "yellow, then red"],
                   ["Sanitiser near MQ-3", "yellow, then red"],
                   ["Hot air on DHT11", "red: OVERHEAT"],
                   ["Probe in water", "red: WATER LEAK"],
                   ["Unplugged a sensor", "'not connected'"]], [55, 45], s, base["theme"])
    poster(OUT / "Electronics_Chart_2_How_It_Works.pdf", dict(base, n="2",
        subtitle="Wiring, the program's decisions and our test results",
        tagline="Reads every sensor 4 times a second  ·  limits saved through power cuts"), [
        (150, [(0.5, "Wiring", [wiring, Spacer(1, 10), Paragraph(
            "Analog sensors use ADC1 (GPIO 0-4): ADC2 stops working while WiFi is on. GPIO 2 and 9 stay empty - they are boot pins.", s["body"])]),
               (0.5, "What the program does", [Steps([
            "Read MQ-5, MQ-3, soil (average of 8)", "Read DHT11 every 2 s", "? Pin floating? -> 'not connected'",
            "? Warming up? no gas alarm for 60 s", "Compare with the profile's limits", "? Danger -> red strobe",
            "? Warning -> yellow blink", "Safe -> green, update phone"], base["theme"])])]),
        (165, [(0.62, "Test: leak, spill and flood", img(ASSETS / "electronics_response.png", 240, s,
            "The firmware's own logic replayed. The bottom strip shows which LED was lit.")),
               (0.38, "Bench tests", [tests])]),
        (108, [(0.5, "Clever bits", bullets([
            "<b>Unplugged check:</b> pull-up, then pull-down - a loose pin swings wildly.",
            "<b>3 profiles:</b> Household, Hotel kitchen, Industrial.",
            "<b>LED test</b> at power-up and from the phone."], s)),
               (0.5, "Phone dashboard", bullets([
            "Join WiFi <b>HazardGuard-C3</b> (no password).",
            "It opens <b>192.168.4.1</b> by itself.",
            "Live gauges, history, LED mirror, limits."], s))]),
        (62, [(1.0, "Next steps", [Paragraph(
            "Relay to start an exhaust fan or close the gas valve  ·  buzzer and flame sensor  ·  SMS alerts  ·  battery backup",
            s["big"])])]),
    ])


def iot():
    base = dict(title="Fish Quality Monitor", theme="#0f766e", theme2="#115e59", tint="#f0fdfa", paper="#f7fdfc",
                category="Internet of Things", board="NodeMCU ESP8266",
                footer="Marine Fish Quality Monitor - IoT supervision of a fishing boat's fish hold")
    s = st(base["theme"])
    dangers = table([["What goes wrong", "Why it matters", "Sensor"],
                     ["Ice runs out", "above 0 °C bacteria multiply fast", "DHT11"],
                     ["Drain outlet blocks", "fish soak in dirty meltwater", "HC-SR04"],
                     ["Fish start to rot", "ammonia, amines ('fishy' smell)", "MQ-135"],
                     ["Deep decay", "methane gas forms", "MQ-4"]], [46, 74, 26], s, base["theme"])
    parts = table([["Part", "Job", "Rs."],
                   ["NodeMCU ESP8266", "brain, log, WiFi", "280"],
                   ["TM1637 display", "summary, fault codes", "90"],
                   ["DHT11", "ice temperature", "110"],
                   ["HC-SR04", "meltwater height", "90"],
                   ["MQ-135", "ammonia / amines", "160"],
                   ["MQ-4", "methane", "160"],
                   ["Red LED, resistors", "alarm light", "10"],
                   ["5 V supply", "power", "150"],
                   ["Total", "", "1,050"]], [46, 46, 20], s, base["theme"], compact=True)
    poster(OUT / "IoT_Chart_1_The_Idea.pdf", dict(base, n="1",
        subtitle="Keeping the catch fresh on a fishing boat - watched from the owner's phone",
        tagline="Ice · Meltwater · Spoilage gas  →  box display  +  phone dashboard  +  voyage log"), [
        (100, [(0.5, "The problem", bullets([
            "The catch sits in a closed hold full of crushed ice.",
            "Ice melts, drains block, fish rot - unseen.",
            "The crew finds out only at the harbour.",
            "By then the catch has lost its price."], s)),
               (0.5, "Our idea", bullets([
            "Sensors watch the hold <b>all the time</b> and log it.",
            "A box display shows a summary, <b>flashes</b> on trouble.",
            "The owner sees it all on a <b>phone or laptop</b>.",
            "No internet: the board makes its own WiFi."], s))]),
        (170, [(1.0, "Inside the fish hold", [Drawing(372, 120, draw_fish_hold)])]),
        (135, [(0.55, "Three dangers, four sensors", [dangers]),
               (0.45, "Parts we used", [parts])]),
        (118, [(1.0, "How the parts connect", [blocks(["DHT11  ice temp", "HC-SR04  water", "MQ-135  ammonia", "MQ-4  methane"],
            "NodeMCU\nfreshness score\n+ log + hotspot", ["TM1637  summary", "Red LED  alarm", "Phone dashboard", "CSV voyage log"], base["theme"])])]),
    ])
    codes = table([["Box shows", "Meaning", "Do this"],
                   ["ICE", "hold too warm", "add crushed ice"],
                   ["drAn", "meltwater too high", "clear the drain"],
                   ["nH3", "ammonia high", "check for rotting fish"],
                   ["CH4", "methane", "remove spoiled fish"],
                   ["E-dH, E-US, E-nH", "sensor not answering", "check the wire"]], [30, 38, 40], s, base["theme"], compact=True)
    score = table([["Freshness starts at 100, minus", "Pts"],
                   ["each °C above 0 °C", "6"], ["each cm of water above 2 cm", "10"],
                   ["MQ-135 above clean air (per 7)", "1"], ["MQ-4 methane trip", "25"]], [80, 16], s, base["theme"])
    wiring = table([["Part", "NodeMCU pin"],
                    ["TM1637 CLK / DIO", "D5 / D6"], ["DHT11", "D4"], ["HC-SR04 TRIG / ECHO", "D7 / D8*"],
                    ["MQ-135 AO", "A0"], ["MQ-4 DO", "D1"], ["Red LED", "D0"]], [60, 36], s, base["theme"], compact=True)
    poster(OUT / "IoT_Chart_2_How_It_Works.pdf", dict(base, n="2",
        subtitle="Freshness score, box display codes, phone dashboard and a simulated voyage",
        tagline="Join WiFi  Boat-Fish-Monitor  →  open 192.168.4.1  →  see the hold live"), [
        (190, [(0.6, "Test: a simulated voyage", img(ASSETS / "iot_story.png", 205, s,
            "The firmware's own simulator: ice melts, the drain blocks, fish rot, then fresh ice.")),
               (0.4, "Box display codes", [codes])]),
        (130, [(0.44, "Freshness score", [score, Spacer(1, 10), Paragraph(
            "80+ <b>FRESH</b> \u00b7 60+ <b>GOOD</b> \u00b7 40+ <b>CHECK</b> \u00b7 below 40 <b>SPOILED</b>", s["body"])]),
               (0.56, "What the program does", [Steps([
            "Read DHT11, HC-SR04, MQ-135, MQ-4", "? Sensor missing? -> E-code, NO SENSOR",
            "Compare with the limits", "Work out the freshness score", "? All fine -> slide through summary",
            "? Problem -> flash code + red LED", "Log a row every minute"], base["theme"])])]),
        (120, [(0.46, "Wiring", [wiring, Spacer(1, 8), Paragraph("* ECHO through a 1 k\u03a9 / 2 k\u03a9 divider.", s["body"])]),
               (0.54, "Logging & simulator", bullets([
            "CSV log in flash; download it from the phone.",
            "Laptop <b>simulator</b>: sliders beside the dashboard.",
            "Voyage story plays every alarm in 4 min."], s))]),
        (62, [(1.0, "Next steps", [Paragraph(
            "DS18B20 probe for exact ice temperature  \u00b7  GSM / LoRa alerts to the owner on shore  \u00b7  automatic drain pump", s["big"])])]),
    ])


def robotics():
    base = dict(title="MarkerPilot", theme="#1d4ed8", theme2="#1e3a8a", tint="#eff6ff", paper="#f8faff",
                category="Robotics", board="ESP32 car + ESP32-C3 gateway",
                footer="MarkerPilot - a self-driving robot car guided by a ceiling camera and reinforcement learning")
    s = st(base["theme"])
    parts = table([["Part", "Job", "Rs."],
                   ["ESP32-WROOM-32", "car: motors + sensors", "420"],
                   ["ESP32-C3 SuperMini", "USB radio gateway", "300"],
                   ["L298N", "motor driver", "180"],
                   ["2 geared DC motors", "wheels", "160"],
                   ["3 x HC-SR04", "obstacles L / F / R", "270"],
                   ["1080p USB webcam", "ceiling camera", "1,200"],
                   ["2S Li-ion battery", "power", "360"],
                   ["Chassis, markers, wires", "", "370"],
                   ["Total", "", "3,260"]], [50, 46, 20], s, base["theme"], compact=True)
    poster(OUT / "Robotics_Chart_1_The_Idea.pdf", dict(base, n="1",
        subtitle="A robot car that drives itself, guided by one camera on the ceiling",
        tagline="Camera sees  →  laptop thinks  →  radio  →  car drives"), [
        (100, [(0.5, "The problem", bullets([
            "Warehouse robots need costly sensors (LiDAR, encoders).",
            "Wheel slip makes their position drift.",
            "Too expensive for schools and small shops."], s)),
               (0.5, "Our idea", bullets([
            "One cheap <b>ceiling camera</b> sees the whole floor.",
            "A printed <b>ArUco marker</b> shows where the car is.",
            "Click anywhere - the car drives there."], s))]),
        (140, [(1.0, "How the car is seen", [Drawing(360, 112, draw_ceiling_camera)])]),
        (140, [(0.5, "Parts we used", [parts]),
               (0.5, "What makes it smart", bullets([
            "<b>Kalman filter</b>: smooth position, predicts 0.08 s ahead.",
            "<b>Two brains</b>: classic controller and an <b>RL agent</b> that learned by practice.",
            "<b>Safety</b>: sonars steer round obstacles; the car refuses to hit anything close.",
            "<b>Simulator</b> with real ArUco pictures."], s))]),
        (118, [(1.0, "How the parts connect", [blocks(["Ceiling camera", "ArUco markers", "Mouse click / goal", "3 sonars (by radio)"],
            "Laptop app\nMarkerPilot\nvision + brain", ["USB gateway (C3)", "ESP-NOW radio", "ESP32 car + L298N", "2 wheel motors"], base["theme"])])]),
    ])
    poster(OUT / "Robotics_Chart_2_How_It_Works.pdf", dict(base, n="2",
        subtitle="Every camera frame: see, filter, decide, stay safe, drive",
        tagline="30 decisions every second  ·  ESP-NOW radio  ·  Windows, Linux and macOS app"), [
        (150, [(0.48, "Every camera frame", [Steps([
            "Grab a camera frame (30 / s)", "Find the ArUco markers", "Kalman filter: position, speed, heading",
            "Pick target: click or goal marker", "? Brain: classic or RL agent", "? Safety: avoid, detour, escape",
            "Send wheel speeds -> radio -> car"], base["theme"])]),
               (0.52, "Learning to drive (RL)", img(ASSETS / "robotics_rl_learning.png", 175, s,
                "Starting from nothing, the agent learns to reach ~80 % of goals by practising in the simulator."))]),
        (140, [(1.0, "Classic controller vs RL agent", img(ASSETS / "robotics_compare.png", 230, s,
            "300 randomised simulator runs each: different motors, delays, goals and obstacles."))]),
        (140, [(0.56, "A full test run", img(ASSETS / "robotics_trajectory.png", 180, s,
            "Two clicked waypoints, then the goal marker. Dashed = what the camera believed.")),
               (0.44, "Reliable radio (v2)", bullets([
            "Car and gateway <b>pair by themselves</b>.",
            "Motor power <b>ramps</b>: no brown-outs.",
            "Stops if silent for <b>400 ms</b>.",
            "On-car <b>collision guard</b>.",
            "<b>linktest</b>: signal, loss, delay."], s))]),
        (70, [(1.0, "Uses and next steps", [Paragraph(
            "<b>Uses:</b> warehouse and hospital delivery robots · factory floors · classroom AI kit. "
            "<b>Next:</b> camera obstacle detection with A* paths · several cameras · many cars at once.", s["big"])])]),
    ])


if __name__ == "__main__":
    print("Building exhibition charts...")
    electronics()
    iot()
    robotics()
