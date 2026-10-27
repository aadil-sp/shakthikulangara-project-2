"""Builds the three project reports (PDF) with their diagrams and graphs.

    python3 reports/build_reports.py

Needs: reportlab, matplotlib, numpy, opencv (robotics graphs run the real simulator).
Robotics graphs use real simulator runs of the MarkerPilot code; the electronics
graph replays the firmware's alarm logic; the IoT graph replays the fish monitor's
voyage-story simulator and alarm formulas.
"""

import json
import math
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "robotics"))
ASSETS.mkdir(exist_ok=True)


# =============================================================================
# Diagram helpers
# =============================================================================
def block_diagram(path, title, center, inputs, outputs, color):
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=170)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")

    def box(x, y, w, h, text, fc, fs=9, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.15", fc=fc, ec="#334155", lw=1.2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, weight="bold" if bold else "normal", wrap=True)

    box(3.7, 2.2, 2.6, 1.6, center, color, 10, True)
    for items, x, side in ((inputs, 0.2, "in"), (outputs, 7.3, "out")):
        n = len(items)
        for i, label in enumerate(items):
            y = 5.2 - i * (5.0 / max(n, 1)) - 0.25
            box(x, y - 0.3, 2.5, 0.62, label, "#f1f5f9", 8)
            start = (x + 2.5, y) if side == "in" else (6.3, 3.0)
            end = (3.7, 3.0) if side == "in" else (x, y)
            ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=11, color="#475569", lw=1.0,
                                         connectionstyle="arc3,rad=0.0"))
    ax.text(5, 5.85, title, ha="center", fontsize=11, weight="bold")
    ax.text(1.45, 0.05, "INPUTS (sensors)", ha="center", fontsize=8, color="#64748b")
    ax.text(8.55, 0.05, "OUTPUTS", ha="center", fontsize=8, color="#64748b")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def flowchart(path, steps, color):
    fig, ax = plt.subplots(figsize=(5.2, 0.95 * len(steps) + 0.4), dpi=170)
    ax.set_xlim(0, 6)
    ax.set_ylim(0, len(steps) * 1.0 + 0.2)
    ax.axis("off")
    for i, (text, kind) in enumerate(steps):
        y = len(steps) - i - 0.5
        fc = color if kind == "decision" else "#e2e8f0" if kind == "end" else "#f8fafc"
        style = "round,pad=0.04,rounding_size=0.35" if kind in ("end",) else "round,pad=0.04,rounding_size=0.1"
        ax.add_patch(FancyBboxPatch((0.6, y - 0.32), 4.8, 0.64, boxstyle=style, fc=fc, ec="#334155", lw=1.1))
        ax.text(3, y, text, ha="center", va="center", fontsize=8.2)
        if i < len(steps) - 1:
            ax.add_patch(FancyArrowPatch((3, y - 0.33), (3, y - 0.67), arrowstyle="-|>", mutation_scale=10, color="#475569"))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# =============================================================================
# Graphs with real data
# =============================================================================
def robotics_graphs():
    from markerpilot.config import AppConfig
    from markerpilot.control.rl import QAgent
    from markerpilot.engine import Engine
    from markerpilot.sim.env import evaluate
    from markerpilot.sim.world import SimWorld

    # 1. RL learning curve (agent trained from an empty Q-table)
    curve = json.loads((HERE / "data" / "rl_from_scratch_curve.json").read_text())["curve"]
    xs = [c[0] for c in curve]
    ys = [max(0.0, c[1]) * 100 for c in curve]
    best = [max(ys[: i + 1]) for i in range(len(ys))]
    fig, ax = plt.subplots(figsize=(7.5, 3.4), dpi=170)
    ax.plot(xs, ys, "o-", color="#94a3b8", lw=1.2, ms=3.5, label="score at each check")
    ax.plot(xs, best, "-", color="#2563eb", lw=2.4, label="best agent so far (kept)")
    ax.set_xlabel("Training episodes in the simulator")
    ax.set_ylabel("Validation score (%)")
    ax.set_title("Reinforcement learning: the car learns to drive from zero", fontsize=11, weight="bold")
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(ASSETS / "robotics_rl_learning.png")
    plt.close(fig)

    # 2. Classic vs RL in randomised scenarios
    agent = QAgent()
    agent.load_best()
    results = {}
    for obs in (False, True):
        for pol in ("classic", "rl"):
            results[(obs, pol)] = evaluate(pol, 300, seed=2024, agent=agent, obstacles=obs)
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.1), dpi=170)
    labels = ["Open floor", "With obstacles"]
    for k, (metric, title, unit) in enumerate((("success_rate", "Goals reached", "%"), ("mean_time_s", "Average time to goal", "s"))):
        ax = axes[k]
        for j, (pol, color) in enumerate((("classic", "#64748b"), ("rl", "#2563eb"))):
            vals = [results[(o, pol)][metric] * (100 if unit == "%" else 1) for o in (False, True)]
            bars = ax.bar([i + j * 0.38 for i in range(2)], vals, 0.36, color=color, label="Classic" if pol == "classic" else "RL agent")
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.0f}" if unit == "%" else f"{v:.1f}", ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks([0.19, 1.19])
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_title(f"{title} ({unit})", fontsize=9.5, weight="bold")
        ax.grid(axis="y", alpha=0.3)
        if unit == "%":
            ax.set_ylim(0, 110)
    axes[0].legend(fontsize=7.5, loc="lower left")
    fig.tight_layout()
    fig.savefig(ASSETS / "robotics_compare.png")
    plt.close(fig)

    # 3. A real end-to-end run (camera image -> vision -> EKF -> controller)
    cfg = AppConfig()
    world = SimWorld(seed=8)
    world.car.reset(30, 85, -0.4)
    world.goal = (170, 25)
    engine = Engine(cfg)
    engine.add_waypoint(*world.renderer.to_px(95, 30), append=False)
    engine.add_waypoint(*world.renderer.to_px(120, 90), append=True)
    true_path, est_path, t = [], [], 0.0
    while t < 25 and engine.arrivals < 3:
        out = engine.process(world.frame(), t, world.car.sonar())
        world.car.command(*out.pwm)
        world.step(1 / 30)
        t += 1 / 30
        true_path.append((world.car.x, world.car.y))
        if out.pose:
            est_path.append(world.renderer.to_cm(out.pose.x, out.pose.y))
    fig, ax = plt.subplots(figsize=(7.5, 4.1), dpi=170)
    ax.plot(*zip(*true_path), color="#0f172a", lw=2.2, label="true path (simulator)")
    ax.plot(*zip(*est_path), "--", color="#f97316", lw=1.2, label="position seen by camera + Kalman filter")
    for (x, y), name in (((95, 30), "waypoint 1"), ((120, 90), "waypoint 2"), (world.goal, "goal marker")):
        ax.plot(x, y, "o", ms=11, mfc="none", mec="#16a34a", mew=2)
        ax.text(x + 3, y - 3, name, fontsize=8, color="#166534")
    ax.plot(30, 85, "s", color="#2563eb", ms=8)
    ax.text(32, 92, "start", fontsize=8, color="#1e3a8a")
    ax.set_xlim(0, 200)
    ax.set_ylim(112.5, 0)
    ax.set_aspect("equal")
    ax.set_xlabel("x (cm)")
    ax.set_ylabel("y (cm)")
    ax.set_title(f"Full system test: two clicked waypoints, then the goal marker ({t:.1f} s)", fontsize=10, weight="bold")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7.5, loc="lower right")
    fig.tight_layout()
    fig.savefig(ASSETS / "robotics_trajectory.png")
    plt.close(fig)
    return results, t


def electronics_graph():
    """Replays the firmware's evaluate() / signal() logic (Household profile) on a simulated incident."""
    th = dict(mq5=(1600, 2500), mq3=(1600, 2500), temp=(40.0, 52.0), soil=(60, 80))
    rng = random.Random(3)
    t = [i * 0.5 for i in range(0, 361)]
    mq5, mq3, temp, soil, level = [], [], [], [], []
    for s in t:
        g5 = 900 + rng.uniform(-25, 25)          # clean-air MQ-5 measured ~900 on the real board
        if 20 <= s < 45: g5 += (s - 20) / 25 * 2200
        elif 45 <= s < 55: g5 += 2200
        elif s >= 55: g5 += 2200 * math.exp(-(s - 55) / 5)
        g3 = 800 + rng.uniform(-25, 25)
        if 85 <= s < 100: g3 += (s - 85) / 15 * 1100
        elif 100 <= s < 110: g3 += 1100
        elif s >= 110: g3 += 1100 * math.exp(-(s - 110) / 4)
        tc = 31 + rng.uniform(-0.3, 0.3)
        sp = 3 + rng.uniform(-1, 1)
        if 130 <= s < 150: sp += (s - 130) / 20 * 85
        elif s >= 150: sp += 85
        sp = max(0, min(100, sp))
        lv = 0
        for v, (w, a) in ((g5, th["mq5"]), (g3, th["mq3"]), (tc, th["temp"]), (sp, th["soil"])):
            lv = max(lv, 2 if v >= a else 1 if v >= w else 0)
        mq5.append(g5); mq3.append(g3); temp.append(tc); soil.append(sp); level.append(lv)
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(7.5, 5.2), dpi=170, sharex=True, gridspec_kw={"height_ratios": [2.4, 1.5, 0.9]})
    a1.plot(t, mq5, color="#ea580c", lw=1.8, label="MQ-5 LPG (ADC)")
    a1.plot(t, mq3, color="#7c3aed", lw=1.8, label="MQ-3 alcohol (ADC)")
    a1.axhline(1600, color="#eab308", ls="--", lw=1.1, label="warning 1600")
    a1.axhline(2500, color="#dc2626", ls="--", lw=1.1, label="danger 2500")
    a1.set_ylabel("ADC 0-4095")
    a1.legend(fontsize=7, loc="lower right", ncol=4)
    a2.plot(t, soil, color="#2563eb", lw=1.8, label="floor moisture (%)")
    a2.axhline(60, color="#eab308", ls="--", lw=1.1)
    a2.axhline(80, color="#dc2626", ls="--", lw=1.1)
    a2.set_ylabel("%")
    a2.legend(fontsize=7, loc="upper left")
    cols = {0: "#16a34a", 1: "#eab308", 2: "#dc2626"}
    for k in range(len(t) - 1):
        a3.axvspan(t[k], t[k + 1], color=cols[level[k]], lw=0)
    a3.set_yticks([])
    a3.set_ylabel("LED", rotation=0, labelpad=14, va="center")
    a3.set_xlabel("Time (s)")
    for a in (a1, a2):
        a.grid(alpha=0.3)
    for x, txt in ((37, "LPG leak"), (100, "spilt sanitiser"), (150, "water on floor")):
        a1.annotate(txt, (x, 3350), ha="center", fontsize=7.5, color="#334155")
    a1.set_ylim(0, 3600)
    fig.suptitle("Alarm logic replay (Household profile): which LED is lit", fontsize=10, weight="bold")
    fig.tight_layout()
    fig.savefig(ASSETS / "electronics_response.png")
    plt.close(fig)


def iot_story():
    """Replays the firmware's voyage-story simulator and alarm logic (same formulas as fish_quality_monitor.ino)."""
    def ramp(t, t0, t1, a, b):
        if t <= t0:
            return a
        if t >= t1:
            return b
        k = (t - t0) / (t1 - t0)
        return a + (b - a) * k * k * (3 - 2 * k)

    tw, td, ww, wd, gw, gd, clean = 1.0, 4.0, 2.0, 5.0, 550, 750, 420
    rng = random.Random(7)
    out = []
    for i in range(0, 241):
        t = float(i)
        temp = ramp(t, 40, 80, 0.4, 3.0)
        if t >= 80: temp = ramp(t, 80, 130, 3.0, 2.0)
        if t >= 150: temp = ramp(t, 150, 195, 2.0, 5.5)
        if t >= 200: temp = ramp(t, 200, 225, 5.5, 0.4)
        water = ramp(t, 40, 80, 0.8, 1.8)
        if t >= 80: water = ramp(t, 80, 125, 1.8, 7.0)
        if t >= 130: water = ramp(t, 130, 145, 7.0, 1.0)
        if t >= 200: water = ramp(t, 200, 215, 1.0, 0.8)
        gas = 420.0
        if t >= 150: gas = ramp(t, 150, 195, 420, 860)
        if t >= 200: gas = ramp(t, 200, 220, 860, 420)
        temp += rng.uniform(-0.15, 0.15)
        water = max(0.0, water + rng.uniform(-0.15, 0.15))
        gas = int(gas + rng.uniform(-8, 8))
        mq5 = 178 <= t < 205
        wet = False   # no soil probe fitted
        lv = lambda v, w, d: 2 if v > d else 1 if v > w else 0
        tl, wl, gl = lv(temp, tw, td), lv(water, ww, wd), lv(gas, gw, gd)
        if wet and wl == 0: wl = 1
        if mq5: gl = 2
        score = 100.0
        if temp > 0: score -= temp * 6
        if water > ww: score -= (water - ww) * 10
        if wet: score -= 8
        if gas > clean: score -= (gas - clean) / 7.0
        if mq5: score -= 25
        codes = [c for c, on in (("ICE", tl), ("drAn", wl), ("nH3", gas > gw), ("CH4", mq5)) if on]
        out.append(dict(t=t, temp=temp, water=water, gas=gas, mq5=mq5, wet=wet, level=max(tl, wl, gl),
                        score=max(0, min(100, round(score))), codes=codes))
    return out


def iot_graph():
    data = iot_story()
    t = [d["t"] for d in data]
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(7.5, 6.2), dpi=170, sharex=True, gridspec_kw={"height_ratios": [2.2, 1.6, 1.4]})
    phases = [(0, 40, "fresh"), (40, 80, "ice melting"), (80, 130, "drain blocked"), (130, 150, "outlet\ncleared"),
              (150, 200, "fish rotting"), (200, 240, "fresh ice")]
    for a in (a1, a2, a3):
        for i, (x0, x1, _) in enumerate(phases):
            if i % 2:
                a.axvspan(x0, x1, color="#e2e8f0", alpha=0.5, lw=0)
        a.grid(alpha=0.3)
    top = a1.secondary_xaxis("top")
    top.set_xticks([(x0 + x1) / 2 for x0, x1, _ in phases])
    top.set_xticklabels([n for _, _, n in phases], fontsize=7, color="#475569")
    top.tick_params(length=0)
    a1.plot(t, [d["temp"] for d in data], color="#dc2626", lw=1.8, label="hold temperature (\u00b0C)")
    a1.plot(t, [d["water"] for d in data], color="#2563eb", lw=1.8, label="meltwater height (cm)")
    a1.axhline(1.0, color="#dc2626", ls=":", lw=1, label="ice limit 1 \u00b0C")
    a1.axhline(5.0, color="#2563eb", ls="--", lw=1, label="drain-blocked limit 5 cm")
    a1.set_ylim(0, 8)
    a1.legend(fontsize=6.8, loc="upper left", ncol=2)
    fig.suptitle("Voyage-story replay of the firmware: readings, alarms and freshness", fontsize=10, weight="bold")
    a2.plot(t, [d["gas"] for d in data], color="#7c3aed", lw=1.8, label="MQ-135 ammonia / amines (ADC)")
    a2.axhline(550, color="#d97706", ls="--", lw=1, label="warning 550")
    a2.axhline(750, color="#dc2626", ls="--", lw=1, label="danger 750")
    a2.fill_between(t, 0, [1000 if d["mq5"] else 0 for d in data], color="#dc2626", alpha=0.12, step="post", label="MQ-4 methane tripped")
    a2.set_ylim(0, 1000)
    a2.legend(fontsize=6.8, loc="upper left")
    a3.plot(t, [d["score"] for d in data], color="#059669", lw=2, label="freshness score")
    a3.step(t, [d["level"] * 50 for d in data], color="#334155", where="post", lw=1, label="alarm (0 ok / 50 warn / 100 danger)")
    a3.set_ylim(-5, 105)
    a3.set_xlabel("Time (s)")
    a3.legend(fontsize=6.8, loc="lower left")
    fig.tight_layout()
    fig.savefig(ASSETS / "iot_story.png")
    plt.close(fig)
    # first moment each display code appears
    first = {}
    for d in data:
        for c in d["codes"]:
            first.setdefault(c, d)
    return data, first


# =============================================================================
# PDF helpers
# =============================================================================
def styles(theme):
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontSize=20, leading=24, textColor=colors.HexColor(theme), spaceAfter=4),
        "subtitle": ParagraphStyle("st", parent=ss["Normal"], fontSize=10.5, alignment=TA_CENTER, textColor=colors.HexColor("#475569")),
        "h": ParagraphStyle("h", parent=ss["Heading2"], fontSize=12.5, textColor=colors.HexColor(theme), spaceBefore=10, spaceAfter=2),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("b", parent=ss["Normal"], fontSize=10, leading=14.2, alignment=TA_JUSTIFY, spaceAfter=4),
        "bullet": ParagraphStyle("bu", parent=ss["Normal"], fontSize=10, leading=14, leftIndent=12, bulletIndent=2, spaceAfter=1),
        "cap": ParagraphStyle("c", parent=ss["Normal"], fontSize=8.5, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"), spaceAfter=8),
        "cell": ParagraphStyle("cell", parent=ss["Normal"], fontSize=8.4, leading=10.5),
        "cellb": ParagraphStyle("cellb", parent=ss["Normal"], fontSize=8.4, leading=10.5, textColor=colors.white, fontName="Helvetica-Bold"),
    }


def table(rows, widths, st, theme):
    data = [[Paragraph(str(c), st["cellb"] if r == 0 else st["cell"]) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def image(path, width_mm):
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(str(path)).getSize()
    return Image(str(path), width=width_mm * mm, height=width_mm * mm * h / w)


def build(pdf, spec):
    theme = spec["theme"]
    st = styles(theme)

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
        canvas.setLineWidth(0.5)
        if doc.page > 1:
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(colors.HexColor(theme))
            canvas.drawString(18 * mm, 287 * mm, "SCIENCE FAIR PROJECT REPORT")
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#64748b"))
            canvas.drawRightString(192 * mm, 287 * mm, f"Category: {spec['category']}")
            canvas.line(18 * mm, 285.5 * mm, 192 * mm, 285.5 * mm)
        canvas.line(18 * mm, 13 * mm, 192 * mm, 13 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(18 * mm, 9 * mm, spec["short"])
        canvas.drawRightString(192 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=spec["title"], author="Science fair team")
    s = []
    s.append(Paragraph(spec["title"], st["title"]))
    s.append(Paragraph(spec["subtitle"], st["subtitle"]))
    s.append(Spacer(1, 6))
    s.append(table([["Category", "Level", "Main board"], [spec["category"], "High school", spec["board"]]], [58 * mm, 50 * mm, 66 * mm], st, theme))
    s.append(Spacer(1, 4))

    n = 0
    for sec in spec["sections"]:
        n += 1
        block = [Paragraph(f"{n}. {sec['h'].upper()}", st["h"]),
                 HRFlowable(width="100%", thickness=0.7, color=colors.HexColor(theme), spaceAfter=4)]
        for item in sec["items"]:
            kind = item[0]
            if kind == "p":
                block.append(Paragraph(item[1], st["body"]))
            elif kind == "ul":
                block += [Paragraph(x, st["bullet"], bulletText="•") for x in item[1]]
            elif kind == "h3":
                block.append(Paragraph(item[1], st["h3"]))
            elif kind == "table":
                block.append(table(item[1], [w * mm for w in item[2]], st, theme))
                block.append(Paragraph(item[3], st["cap"]))
            elif kind == "img":
                block.append(KeepTogether([image(item[1], item[2]), Paragraph(item[3], st["cap"])]))
            elif kind == "break":
                block.append(PageBreak())
        s += block
    doc.build(s, onFirstPage=decorate, onLaterPages=decorate)
    print(f"  wrote {pdf.relative_to(ROOT)}")


# =============================================================================
# Report content
# =============================================================================
def robotics_spec(results, run_t):
    r = results
    pct = lambda o, p: f"{r[(o, p)]['success_rate'] * 100:.0f}%"
    sec = lambda o, p: f"{r[(o, p)]['mean_time_s']:.1f} s"
    block_diagram(ASSETS / "robotics_block.png", "MarkerPilot system", "Laptop app\n(MarkerPilot)\nvision + brain",
                  ["Ceiling USB camera", "ArUco marker on car", "Goal marker / mouse click", "3 ultrasonic sensors\n(via radio)"],
                  ["ESP32-C3 USB gateway", "ESP-NOW radio", "ESP32 car + L298N", "2 DC gear motors"], "#bfdbfe")
    flowchart(ASSETS / "robotics_flow.png", [
        ("Camera frame (30 per second)", "end"), ("Find ArUco markers: car + goal", "step"),
        ("Kalman filter: smooth position, speed, heading", "step"), ("Pick target: clicked point or goal marker", "step"),
        ("Brain: classic controller OR RL agent", "decision"), ("Safety: ultrasonic avoid / detour / escape", "decision"),
        ("Auto-fix reversed motors, smooth the command", "step"), ("Send wheel speeds over USB -> radio -> car", "step"),
        ("Arrived? next waypoint, else repeat", "end")], "#bfdbfe")
    return {
        "title": "MarkerPilot: A Self-Driving Robot Car Guided by a Ceiling Camera and Reinforcement Learning",
        "subtitle": "Overhead ArUco-marker localisation, Kalman filtering, Q-learning and ESP-NOW radio control",
        "short": "MarkerPilot - camera-guided robot car", "category": "Robotics", "board": "ESP32 + ESP32-C3", "theme": "#1d4ed8",
        "sections": [
            {"h": "Abstract", "items": [("p",
                "MarkerPilot is a small robot car that drives itself to any point I click on a laptop screen, or to a printed "
                "goal marker placed on the floor. A USB camera on the ceiling watches the floor. A printed ArUco marker on top of "
                "the car tells the computer exactly where the car is and which way it faces, 30 times every second. A Kalman "
                "filter cleans up the camera measurements and predicts the car's position a little into the future to cancel "
                "radio and camera delay. The driving decision is made either by a classic controller or by a reinforcement-learning "
                "agent that learned to drive by practising thousands of times in a simulator. Commands travel from the laptop to "
                "an ESP32-C3 USB stick and then over the ESP-NOW radio to the ESP32 on the car. Three ultrasonic sensors on the car "
                "let it slow down, steer around and back away from obstacles, and the car itself refuses to drive forward into "
                "something closer than a safe distance even if the radio link drops a command. "
                f"In 300 randomised simulator tests the system reached "
                f"{pct(False, 'classic')} of goals on an open floor and {pct(True, 'classic')} with obstacles in the way.")]},
            {"h": "Aim of the project", "items": [("ul", [
                "Build a two-wheel robot car controlled by an ESP32 over the low-delay ESP-NOW radio.",
                "Track the car's position and heading using only a ceiling camera and a printed ArUco marker.",
                "Make the car drive smoothly to clicked waypoints or to a goal marker, and stop accurately.",
                "Teach a reinforcement-learning (RL) agent to drive, and compare it fairly with a classic controller.",
                "Build a realistic simulator so everything can be tested without the real car.",
                "Make a desktop app that runs on Windows, Linux and macOS and finds every connected camera."])]},
            {"h": "Problem statement and need", "items": [("p",
                "Warehouse and hospital robots usually carry expensive sensors (LiDAR, wheel encoders, cameras) to know where they are, "
                "and wheel slip makes their position estimate drift. A single cheap camera on the ceiling can see the whole floor at "
                "once with no drift at all. The robot itself then only needs motors, a cheap microcontroller and simple ultrasonic "
                "sensors. This makes the robot light, cheap and easy for schools and small workshops to build.")]},
            {"h": "Components used and cost", "items": [("table", [
                ["Component", "Model", "Qty", "Purpose", "Approx. cost"],
                ["Car controller", "ESP32-WROOM-32 dev board", "1", "Receives radio commands, drives motors, reads sensors", "Rs. 420"],
                ["USB radio gateway", "ESP32-C3 SuperMini", "1", "Plugs into the laptop, relays commands over ESP-NOW", "Rs. 300"],
                ["Motor driver", "L298N dual H-bridge", "1", "Speed and direction of both motors", "Rs. 180"],
                ["Motors + wheels", "BO geared DC motors", "2", "Left and right drive wheels", "Rs. 160"],
                ["Chassis", "Acrylic base + caster", "1", "Holds the parts", "Rs. 280"],
                ["Ultrasonic sensors", "HC-SR04", "3", "Left (40°), front and right (40°) obstacle sensing", "Rs. 270"],
                ["Camera", "1080p USB webcam", "1", "Mounted on the ceiling looking down", "Rs. 1,200"],
                ["Battery", "2S 7.4 V Li-ion pack", "1", "Powers motors and the ESP32", "Rs. 360"],
                ["Buzzer", "Active buzzer", "1", "Obstacle warning beep", "Rs. 20"],
                ["Markers", "Printed ArUco 4x4 (IDs 0 and 1)", "2", "Car marker and goal marker", "Rs. 10"],
                ["Wires, resistors", "1 kΩ + 2 kΩ per echo line; 100 kΩ + 33 kΩ", "1 set", "Echo dividers, battery-voltage divider", "Rs. 60"],
                ["Total", "", "", "", "Rs. 3,260"]], [30, 38, 11, 68, 25], "Table 1: Bill of materials (approximate local prices)")]},
            {"h": "Circuit connections", "items": [
                ("p", "The ultrasonic ECHO pins give a 5 V pulse but ESP32 pins accept only 3.3 V, so each ECHO line goes through a "
                      "1 kΩ / 2 kΩ voltage divider. The L298N enable jumpers stay on, so the four IN pins carry PWM directly."),
                ("table", [["Part pin", "ESP32 pin", "What it does"],
                           ["L298N IN1 / IN2", "GPIO 27 / 26", "Left motor forward / backward (PWM)"],
                           ["L298N IN3 / IN4", "GPIO 25 / 33", "Right motor forward / backward (PWM)"],
                           ["Left sonar TRIG / ECHO", "GPIO 5 / 18", "Left 40° obstacle distance"],
                           ["Front sonar TRIG / ECHO", "GPIO 22 / 23", "Front obstacle distance"],
                           ["Right sonar TRIG / ECHO", "GPIO 19 / 21", "Right 40° obstacle distance"],
                           ["Buzzer", "GPIO 4", "Beep on command from the app"],
                           ["Battery sense (optional)", "GPIO 34", "Battery + through 100 kΩ / 33 kΩ divider"],
                           ["Status LED", "GPIO 2 (on board)", "Fast flash = searching, slow flash = linked"],
                           ["Gateway (ESP32-C3)", "USB to laptop", "Serial 115200: 'D,l,r' drive, 'G,cm' guard, 'B' beep; replies 'T,...' and 'S,...'"]],
                 [55, 35, 82], "Table 2: Wiring of the car and gateway")]},
            {"h": "System overview", "items": [("img", ASSETS / "robotics_block.png", 165, "Figure 1: Block diagram")]},
            {"h": "How I did this (method)", "items": [
                ("h3", "Step 1 - Seeing the car"),
                ("p", "OpenCV's ArUco detector finds the four corners of each marker. The centre gives the position and the direction from the "
                      "centre to the middle of the top edge gives the heading. The known printed size (5 cm) tells the program how many pixels "
                      "make one centimetre, so distances are shown in real centimetres."),
                ("h3", "Step 2 - Cleaning the measurements (Kalman filter)"),
                ("p", "An Extended Kalman Filter models the car as a unicycle with position, heading, speed and turn rate. It removes jitter, "
                      "estimates speed, keeps tracking for a moment if the marker is hidden by glare, rejects impossible jumps, and predicts "
                      "0.08 s ahead to cancel the delay of the camera and radio."),
                ("h3", "Step 3 - Driving (two brains)"),
                ("p", "The classic controller turns on the spot when the target is more than 55° to the side, otherwise it drives forward "
                      "while steering with a PD controller and brakes smoothly in the last 30 cm. The RL brain is a Q-learning agent: it looks "
                      "at the distance band, the heading-error sector (16 sectors) and the obstacle situation, and picks one of 9 moves such "
                      "as forward, creep-left or spin-right. It gets a reward for every centimetre of progress and for aiming at the goal, a "
                      "big bonus for arriving and penalties for crashing or wasting time."),
                ("h3", "Step 4 - Practising in a simulator"),
                ("p", "I wrote a physics simulator of the car with motor dead-band, motor lag, unequal left/right motors, radio delay and "
                      "ultrasonic sensors. It even draws a fake camera picture with real ArUco markers, so the complete vision pipeline is "
                      "tested. Every training episode uses different random motors, delays, start points, goals and obstacles, so the "
                      "agent cannot just memorise one situation (domain randomisation)."),
                ("h3", "Step 5 - Safety and self-correction"),
                ("p", "A safety layer sits on top of both brains: it slows down and turns away from obstacles, drives a short detour so the "
                      "car does not dither in front of a box, and backs out if the camera sees the car pushing without moving. Echoes "
                      "farther away than the goal are ignored so the car can still reach a goal next to a wall. The app also compares what it "
                      "commanded with what the camera saw: if the car drives backwards or turns the wrong way, it fixes the motor direction "
                      "setting by itself."),
                ("h3", "Step 6 - A reliable radio link (firmware v2)"),
                ("p", "The car and the gateway pair by themselves: packets carry a 'M2' header, and the car answers the first MarkerPilot "
                      "gateway it hears, so no MAC addresses are typed in. The car's three ultrasonic sensors are read with interrupts, "
                      "so the program never waits for an echo and reacts to a new command within a millisecond or two. Motor power is "
                      "ramped (0 to full in about 85 ms) because sudden reversals at full power pulled the battery voltage down and "
                      "reset the ESP32. If no command arrives for 400 ms the motors ramp to a stop. As a last line of defence the car "
                      "itself cuts forward motion when the front sensor sees an obstacle closer than the guard distance set by the app; "
                      "turning and reversing still work so the app can steer away. Every telemetry packet reports the distances, signal "
                      "strength, the motor power actually applied and which command it is answering, so the gateway can measure the "
                      "delay. The command 'markerpilot linktest' prints the signal strength, packet loss, delay and sonar health, and "
                      "can pulse each wheel to check the wiring."),
                ("img", ASSETS / "robotics_flow.png", 95, "Figure 2: What happens in every camera frame")]},
            {"h": "Testing and results", "items": [
                ("p", "All numbers below come from running the real MarkerPilot code in the simulator with randomised car parameters "
                      "(300 episodes each). The end-to-end test uses the rendered camera picture, so the ArUco detection and the Kalman "
                      "filter are part of the test."),
                ("table", [["Test", "Classic controller", "RL agent"],
                           ["Goals reached - open floor", pct(False, "classic"), pct(False, "rl")],
                           ["Average time - open floor", sec(False, "classic"), sec(False, "rl")],
                           ["Goals reached - with obstacles", pct(True, "classic"), pct(True, "rl")],
                           ["Average time - with obstacles", sec(True, "classic"), sec(True, "rl")]],
                 [70, 50, 50], "Table 3: Simulator results (300 randomised episodes per cell)"),
                ("img", ASSETS / "robotics_compare.png", 165, "Figure 3: Classic controller vs RL agent"),
                ("img", ASSETS / "robotics_rl_learning.png", 160,
                 "Figure 4: An RL agent starting from an empty table learns to reach about 80% of goals within a few thousand practice runs. "
                 "The agent shipped with the app starts from simple driving rules and is improved further by training."),
                ("img", ASSETS / "robotics_trajectory.png", 160,
                 f"Figure 5: Full-system test in the simulator: the car visits two clicked waypoints and then the goal marker in {run_t:.1f} s. "
                 "The dashed line is what the camera and Kalman filter believed; it lies on top of the true path."),
                ("p", "Observation: the classic controller is slightly faster; the RL agent is just as reliable on an open floor and learned "
                      "its behaviour from experience instead of hand-tuned rules. Both need the safety layer to get around obstacles, "
                      "because the ultrasonic sensors only see what is in front of the car.")]},
            {"h": "Applications", "items": [("ul", [
                "Warehouse trolleys that follow floor markers to shelves.",
                "Hospital and hotel delivery robots on a fixed floor area.",
                "Classroom kit for teaching computer vision, control and machine learning.",
                "Factory floors where one ceiling camera guides several small robots."])]},
            {"h": "Advantages and limitations", "items": [
                ("ul", ["No position drift: the ceiling camera always knows where the car is.",
                        "Cheap robot: no encoders, LiDAR or on-board camera needed.",
                        "Same code runs in the simulator and on the real car.",
                        "Safe by design: the car stops on its own if the radio goes quiet or an obstacle is too close.",
                        "Limitation: works only inside the camera's view, and needs reasonable lighting.",
                        "Limitation: obstacles are seen only by the ultrasonic sensors, not by the camera."])]},
            {"h": "Future improvements", "items": [("ul", [
                "Detect obstacles in the camera picture and plan a full path around them (A* search).",
                "Use several ceiling cameras for a bigger area.",
                "Control several cars at once, each with its own marker ID.",
                "Replace the Q-table with a small neural network (deep RL) for smoother driving."])]},
            {"h": "Conclusion", "items": [("p",
                "MarkerPilot shows that a single ceiling camera, a printed marker and an ESP32 are enough for accurate autonomous "
                "navigation. The Kalman filter makes the position reliable, the classic controller and the RL agent both drive the car "
                "to its goals, and the simulator made it possible to test and train everything safely before using the real car.")]},
            {"h": "References", "items": [("ul", [
                "OpenCV documentation - Detection of ArUco markers (docs.opencv.org).",
                "Sutton and Barto - Reinforcement Learning: An Introduction (Q-learning).",
                "Thrun, Burgard and Fox - Probabilistic Robotics (Extended Kalman Filter).",
                "Espressif - ESP-NOW protocol documentation (docs.espressif.com)."])]},
        ]}


def electronics_spec():
    block_diagram(ASSETS / "electronics_block.png", "HazardGuard C3", "ESP32-C3\nhazard logic\n+ web server",
                  ["MQ-5 LPG / gas", "MQ-3 alcohol / solvent", "DHT11 temp / humidity", "Soil probe: water leak", "Phone dashboard\n(settings)"],
                  ["Green LED: safe", "Yellow LED: warning", "Red LED: danger", "WiFi hotspot\n192.168.4.1"],
                  "#fed7aa")
    flowchart(ASSETS / "electronics_flow.png", [
        ("Read MQ-5, MQ-3, soil (average of 8) + DHT11", "end"), ("Pin floating? report 'not connected'", "decision"),
        ("Gas sensors warming up? (first 60 s)", "decision"), ("Compare with the active profile's limits", "step"),
        ("Danger: red strobe", "decision"), ("Warning: yellow blink", "decision"),
        ("Safe: green LED", "step"), ("Update phone dashboard, repeat 4 times a second", "end")], "#fed7aa")
    electronics_graph()
    return {
        "title": "HazardGuard C3: Multi-Hazard Alarm with a Phone Dashboard",
        "subtitle": "LPG leak, alcohol / solvent vapour, overheating and water-leak detection with traffic-light LEDs and a password-free WiFi dashboard",
        "short": "HazardGuard C3 - multi-hazard alarm", "category": "Electronics", "board": "ESP32-C3", "theme": "#c2410c",
        "sections": [
            {"h": "Abstract", "items": [("p",
                "HazardGuard C3 is a low-cost alarm for kitchens, hotel boiler rooms and workshops. It watches four hazards at once: "
                "LPG or natural-gas leaks (MQ-5), alcohol, sanitiser or solvent vapour (MQ-3), overheating or fire (DHT11) and water "
                "leaking onto the floor (soil-moisture probe). Three LEDs act like a traffic light: green for safe, a blinking yellow "
                "for a warning and a fast red strobe for danger. The ESP32-C3 also creates its own WiFi hotspot, so any phone can open "
                "a live dashboard at 192.168.4.1 to see every reading, see which sensors are disconnected, switch between Household, "
                "Hotel kitchen and Industrial profiles, test the LEDs and change the alarm limits, which are saved through power cuts.")]},
            {"h": "Aim of the project", "items": [("ul", [
                "Detect gas leaks, solvent vapour, overheating and water leaks with one small board.",
                "Warn clearly with three LEDs that anyone understands at a glance.",
                "Show live readings on any phone with no internet and no app.",
                "Allow different limits for homes, hotels and factories, kept after a power cut.",
                "Never show a made-up value: a disconnected sensor is reported as 'not connected'."])]},
            {"h": "Problem statement and need", "items": [("p",
                "LPG leaks, kitchen fires and burst pipes cause accidents and damage every year, often because nobody notices in time. "
                "Most low-cost alarms watch only one hazard, cannot be checked from another room and give no idea whether their sensor "
                "is even working. HazardGuard C3 watches four hazards, shows them on any phone nearby and tells you when a sensor has "
                "been unplugged.")]},
            {"h": "Components used and cost", "items": [("table", [
                ["Component", "Model", "Qty", "Purpose", "Approx. cost"],
                ["Controller", "ESP32-C3 SuperMini", "1", "Reads sensors, runs logic, WiFi hotspot", "Rs. 300"],
                ["LPG sensor", "MQ-5 module", "1", "LPG / natural-gas leaks", "Rs. 150"],
                ["Alcohol sensor", "MQ-3 module", "1", "Alcohol, sanitiser and solvent vapour", "Rs. 150"],
                ["Temperature sensor", "DHT11", "1", "Overheating / fire, humidity", "Rs. 110"],
                ["Moisture probe", "Soil moisture probe + module", "1", "Water leak / flooding on the floor", "Rs. 80"],
                ["LEDs", "Green, yellow, red 5 mm", "3", "Safe / warning / danger", "Rs. 10"],
                ["Resistors", "220 \u03a9", "3", "LED current limit", "Rs. 5"],
                ["Power", "5 V 2 A USB-C adapter", "1", "Supply (MQ heaters need 5 V)", "Rs. 150"],
                ["Total", "", "", "", "Rs. 955"]], [28, 40, 11, 68, 25], "Table 1: Bill of materials (approximate local prices)")]},
            {"h": "Circuit connections", "items": [
                ("p", "The analog sensors must use the ESP32-C3's ADC1 pins (GPIO 0-4), because ADC2 stops working while WiFi is on. "
                      "GPIO 2 and GPIO 9 are left empty: they decide how the chip boots, and GPIO 9 is the BOOT button. The MQ outputs "
                      "go straight to the pins and the gas limits are set for that; the soil module runs on 3.3 V."),
                ("table", [["Part pin", "ESP32-C3 pin", "Notes"],
                           ["MQ-5 AO", "GPIO 1 (ADC1)", "VCC 5 V, DO not used"],
                           ["MQ-3 AO", "GPIO 4 (ADC1)", "VCC 5 V, DO not used"],
                           ["Soil moisture AO", "GPIO 0 (ADC1)", "VCC 3.3 V, DO not used"],
                           ["DHT11 DATA", "GPIO 6", "VCC 3.3 V"],
                           ["Green LED", "GPIO 7", "220 \u03a9 to GND"],
                           ["Yellow LED", "GPIO 8", "220 \u03a9 to GND"],
                           ["Red LED", "GPIO 3", "220 \u03a9 to GND"]],
                 [45, 35, 92], "Table 2: Wiring")]},
            {"h": "System overview", "items": [("img", ASSETS / "electronics_block.png", 165, "Figure 1: Block diagram")]},
            {"h": "How I did this (method)", "items": [
                ("p", "Each analog sensor is read four times a second and smoothed with a moving average of 8 readings. The soil reading "
                      "is turned into a percentage using two calibration points: the probe in dry air and the probe dipped in water. "
                      "For the first 60 seconds the MQ heaters warm up, so gas alarms are held back and the yellow LED gives a short blip."),
                ("p", "Finding an unplugged sensor is harder than it sounds: a loose analog pin 'floats' and reads random values that look "
                      "real. Once a second the program switches on the chip's internal pull-down resistor, reads the pin, then the "
                      "pull-up, and reads again. A wired sensor barely moves, but a floating pin swings from one end of the scale to the "
                      "other, so it is reported as 'not connected'. The DHT11 is reported after 3 failed readings in a row."),
                ("p", "Each profile has its own limits; the Industrial profile is the most sensitive. The chosen profile and any limits "
                      "edited on the phone are stored in the ESP32's flash memory (Preferences), so they survive power cuts. At power-up "
                      "the LEDs light green, yellow and red in turn so each one can be checked by eye, and the dashboard can light any "
                      "LED on demand."),
                ("img", ASSETS / "electronics_flow.png", 90, "Figure 2: Control flow")]},
            {"h": "Testing and results", "items": [
                ("p", "Figure 3 replays the firmware's decision logic with the Household limits: an LPG leak that is cleared by opening a "
                      "window, a spilt bottle of sanitiser, and then water spreading across the floor. The bottom strip shows which LED "
                      "the controller lights at every moment. On the real board the MQ-5 read about 900 in clean room air, far below the "
                      "1600 warning limit."),
                ("img", ASSETS / "electronics_response.png", 160, "Figure 3: Alarm logic replay"),
                ("table", [["Test on the bench", "Expected result"],
                           ["Power on", "Green, yellow, red light in turn; then green with a yellow blip during warm-up"],
                           ["Gas lighter (unlit) near the MQ-5", "Yellow blink, then red strobe; dashboard: 'LPG / GAS LEAK'"],
                           ["Hand sanitiser near the MQ-3", "Yellow, then red; dashboard: 'ALCOHOL / SOLVENT VAPOUR'"],
                           ["Hot air near the DHT11 above 52 \u00b0C", "Red; dashboard: 'FIRE / OVERHEAT'"],
                           ["Soil probe dipped in a cup of water", "Red; dashboard: 'WATER LEAK / FLOODING'"],
                           ["Unplug any sensor", "Dashboard lists it as not connected; no fake value"]],
                 [70, 102], "Table 3: Bench test checklist")]},
            {"h": "Applications", "items": [("ul", [
                "Home kitchens: LPG leak warning.", "Hotel kitchens and boiler rooms: gas and overheating watch.",
                "Labs, salons and workshops: solvent and sanitiser vapour.", "Bathrooms, store rooms and server rooms: water-leak alarm."])]},
            {"h": "Advantages and limitations", "items": [("ul", [
                "Four hazards on one board for under a thousand rupees.",
                "Works without internet: the phone connects straight to the device.",
                "Tells you when a sensor is unplugged instead of showing a false 'all clear'.",
                "Limitation: it only warns; it does not switch off the gas or start a fan.",
                "Limitation: MQ sensors need warm-up and give relative values, not exact ppm.",
                "Limitation: the DHT11 reads the air, not flames directly; a flame sensor would react faster."])]},
            {"h": "Future improvements", "items": [("ul", [
                "Add a relay to start an exhaust fan or close a gas solenoid valve.", "Add a buzzer and a flame sensor.",
                "Send SMS or app alerts through a home router.", "Battery backup for power cuts."])]},
            {"h": "Conclusion", "items": [("p",
                "HazardGuard C3 watches gas, vapour, heat and water at the same time, shows the result with three simple lights and on "
                "any phone, and is honest about sensors that are not working - all for less than a thousand rupees.")]},
            {"h": "References", "items": [("ul", [
                "Hanwei Electronics - MQ-3 and MQ-5 gas sensor datasheets.", "Aosong - DHT11 datasheet.",
                "Espressif - ESP32-C3 technical reference (ADC, GPIO pull resistors) and Arduino core documentation."])]},
        ]}


def iot_spec(story):
    data, first = story
    block_diagram(ASSETS / "iot_block.png", "Marine Fish Quality Monitor", "NodeMCU\nESP8266\nfreshness logic\n+ hotspot",
                  ["DHT11 ice temperature", "HC-SR04 meltwater height", "MQ-135 ammonia / amines", "MQ-4 methane"],
                  ["TM1637 summary display\n(flashes on fault)", "Red alarm LED (optional)", "Owner's phone / laptop\n192.168.4.1", "Flash log (CSV)"], "#99f6e4")
    flowchart(ASSETS / "iot_flow.png", [
        ("Read sensors (or the simulator)", "end"), ("Sensor missing? show NO SENSOR / E-code", "decision"),
        ("Compare temperature, water and gas with limits", "step"), ("Freshness score 0-100 and grade", "step"),
        ("Normal: TM1637 cycles summary values", "step"), ("Abnormal: flash ICE / drAn / nH3 / CH4 + red LED", "decision"),
        ("Log every minute; phone reads /api/data every second", "end")], "#99f6e4")
    lowest = min(data, key=lambda d: d["score"])
    peak_w = max(data, key=lambda d: d["water"])
    peak_g = max(data, key=lambda d: d["gas"])
    def when(code):
        d = first.get(code)
        return f"{d['t']:.0f} s" if d else "-"
    rows = [["Phase of the voyage", "What the sensors saw", "Box display", "First alarm"],
            ["Fresh catch on ice (0-40 s)", "0.4 °C, 0.8 cm water, MQ-135 ~420", "cycles 0°C / H 1 / nH41 / Fr97", "none"],
            ["Ice melting (40-80 s)", "temperature climbs to 3 °C", "flashes ICE", when("ICE")],
            ["Drain outlet blocked (80-130 s)", f"water rises to {peak_w['water']:.1f} cm", "flashes drAn", when("drAn")],
            ["Outlet cleared (130-150 s)", "water drains back to 1 cm", "ICE only", "-"],
            ["Fish rotting (150-200 s)", f"5.5 °C, MQ-135 up to ~{peak_g['gas']}, MQ-4 trips", "flashes nH3, CH4, ICE", f"{when('nH3')} / {when('CH4')}"],
            ["Fresh ice (200-240 s)", "all values back to normal", "summary again", "cleared"]]
    return {
        "title": "Marine Fish Quality Monitor: IoT Supervision of a Fishing Boat's Fish Hold",
        "subtitle": "Ice temperature, meltwater clogging and spoilage-gas monitoring with a summary display, data logging and a phone dashboard for the boat owner",
        "short": "Marine Fish Quality Monitor - IoT fish-hold supervisor", "category": "Internet of Things", "board": "NodeMCU ESP8266", "theme": "#0f766e",
        "sections": [
            {"h": "Abstract", "items": [("p",
                "Fishing boats keep their catch in an insulated hold packed with crushed ice. Three things ruin the catch at sea: the "
                "ice running out, meltwater that cannot drain because the outlet is blocked so the fish soak in dirty water, and fish "
                "that start to rot. The Marine Fish Quality Monitor watches all three with low-cost sensors on a NodeMCU ESP8266: a "
                "DHT11 for the hold temperature, an ultrasonic sensor for the height of the meltwater, an MQ-135 for the ammonia and "
                "amines given off by rotting fish and an MQ-4 for methane from decomposition. It logs every reading, works out a "
                "freshness score, shows only a short summary on a 4-digit TM1637 display and flashes a fault code on it when anything "
                "goes abnormal. The boat owner joins the board's own WiFi and sees everything live on a phone or laptop. A separate "
                "simulator page lets the whole system be demonstrated without sensors.")]},
            {"h": "Aim of the project", "items": [("ul", [
                "Keep the fish hold at ice temperature (0 °C) and warn when the ice is melting away.",
                "Measure the meltwater height and warn when too much water means the drain outlet is blocked.",
                "Detect the ammonia, amine and methane gases released by rotting fish.",
                "Log the data through the voyage, show a summary on the box and the full picture on the owner's phone or laptop.",
                "Provide a simulator so the system can be shown and tested without sensors."])]},
            {"h": "Problem statement and need", "items": [("p",
                "Fish is one of the most perishable foods. On ice it stays fresh for days, but once the hold rises above 0 °C bacteria "
                "multiply quickly. Melted ice must drain away: if the drain clogs with scales and slime, the bottom layer of fish soaks in "
                "meltwater and spoils fast. Spoiling fish give off ammonia and amines such as trimethylamine (the 'fishy' smell), and "
                "deeper decay produces methane. The crew is busy fishing and the hold is closed, so these problems are often found only "
                "at the harbour, when the catch has already lost its price. A cheap monitor that watches the hold all the time and tells "
                "the owner immediately protects both the catch and the buyer.")]},
            {"h": "Components used and cost", "items": [("table", [
                ["Component", "Model", "Qty", "Purpose", "Approx. cost"],
                ["Controller", "NodeMCU ESP8266 (ESP-12E)", "1", "Reads sensors, logic, logging, hotspot, web server", "Rs. 280"],
                ["Display", "TM1637 4-digit 7-segment", "1", "Summary values; flashes fault codes", "Rs. 90"],
                ["Temperature sensor", "DHT11", "1", "Hold (ice) temperature and humidity", "Rs. 110"],
                ["Ultrasonic sensor", "HC-SR04", "1", "Meltwater height on the hold floor", "Rs. 90"],
                ["Ammonia sensor", "MQ-135 module", "1", "Ammonia / amine level from rotting fish", "Rs. 160"],
                ["Methane sensor", "MQ-4 module", "1", "Methane trip from decomposition", "Rs. 160"],
                ["Indicator (optional)", "Red 5 mm LED + 220 Ω", "1", "Alarm light", "Rs. 5"],
                ["Resistors", "1 kΩ, 2 kΩ", "1 set", "Ultrasonic echo divider", "Rs. 5"],
                ["Power", "5 V 1-2 A USB supply / power bank", "1", "Supply (MQ heaters need 5 V)", "Rs. 150"],
                ["Total", "", "", "", "Rs. 1,050"]], [28, 40, 11, 68, 25], "Table 1: Bill of materials (approximate local prices)")]},
            {"h": "Circuit connections", "items": [
                ("p", "The NodeMCU has only one analog input (A0). The MQ-135 uses it, because the ammonia level is shown as a number; "
                      "the MQ-4 uses the digital output (DO) of its comparator module, set with its potentiometer, as a gas yes / no "
                      "signal. The HC-SR04 echo is a 5 V signal, so it goes through a 1 kΩ / 2 kΩ divider (or the sensor is "
                      "powered from 3.3 V). The TM1637 is mounted upside down in the box, so the firmware rotates every digit by 180°."),
                ("table", [["Part pin", "NodeMCU pin", "Notes"],
                           ["TM1637 CLK / DIO", "D5 / D6", "VCC from VIN (5 V)"],
                           ["DHT11 DATA", "D4", "VCC 3.3 V"],
                           ["HC-SR04 TRIG / ECHO", "D7 / D8", "ECHO through 1 kΩ / 2 kΩ divider"],
                           ["MQ-135 AO", "A0", "VCC 5 V, DO not used"],
                           ["MQ-4 DO", "D1", "VCC 5 V, AO not used"],
                           ["Red LED (optional)", "D0", "through 220 Ω to GND"]],
                 [45, 35, 92], "Table 2: Wiring (full sheet in CONNECTIONS.md)")]},
            {"h": "System overview", "items": [("img", ASSETS / "iot_block.png", 165, "Figure 1: Block diagram")]},
            {"h": "How I did this (method)", "items": [
                ("p", "The ultrasonic sensor is fixed under the lid looking straight down. Meltwater height = (distance to the empty floor) "
                      "- (measured distance); the median of the last five pings ignores splashes from the rolling boat. The DHT11 sits in "
                      "the ice between the fish, and the two gas sensors sit in the air above the catch. The MQ-135 reading is averaged "
                      "over 8 samples; in clean air it reads about 420 on this board. Gas alarms are ignored for the first 60 s while the "
                      "heaters warm up, and the display shows a spinning segment with a countdown."),
                ("p", "A freshness score starts at 100 and loses points for temperature above 0 °C (6 per degree), meltwater above "
                      "2 cm (10 per cm), MQ-135 readings above clean air (1 per 7 counts) and an MQ-4 trip (25). It is graded FRESH, "
                      "GOOD, CHECK or SPOILED. The TM1637 normally slides through the temperature, water height, ammonia level and score, "
                      "with a small water-ripple animation between rounds. When anything is abnormal it flashes a code - ICE, drAn, nH3 "
                      "or CH4 - followed by the value, and the red LED blinks. A missing sensor shows E-dH, E-US or E-nH and appears as "
                      "NO SENSOR on the dashboard, never as a made-up value. Every minute a CSV row is written to the board's flash; the "
                      "dashboard gives the board the real time from the phone, so log rows get real dates."),
                ("img", ASSETS / "iot_flow.png", 90, "Figure 2: Program flow")]},
            {"h": "Simulator", "items": [("p",
                "A separate simulator page runs on any laptop without the board. The full dashboard sits on one side and sliders on the "
                "other: ice temperature, meltwater height, MQ-135 level, humidity and the MQ-4 trip, plus one-tap scenes (fresh catch, "
                "ice melting, drain blocked, rotten fish). A 'voyage story' mode plays a 4-minute trip through every alarm. The simulator "
                "uses exactly the same rules and limits as the firmware. The real board's page has no simulator controls and shows only "
                "live sensor readings; for exhibitions the board can still play the voyage story on its own display.")]},
            {"h": "Testing and results", "items": [
                ("p", "The graph below is a replay of the firmware's own simulator and alarm formulas over one voyage story. Every alarm "
                      f"fires in the right phase and clears afterwards; the freshness score falls to {lowest['score']} at the worst point "
                      f"({lowest['t']:.0f} s, rotting fish without ice) and recovers with fresh ice."),
                ("img", ASSETS / "iot_story.png", 165, "Figure 3: Readings, alarms and freshness during the simulated voyage"),
                ("table", rows, [42, 52, 42, 30], "Table 3: What the monitor reported in each phase"),
                ("p", "On the real board the MQ-135 read about 400-420 in clean room air, well below the 550 warning limit. The firmware "
                      "compiles for the NodeMCU (32 % of flash, 40 % of RAM), and the dashboard and simulator were tested in phone- and "
                      "laptop-sized browsers.")]},
            {"h": "Applications", "items": [("ul", [
                "Fishing boats on multi-day voyages.", "Insulated fish boxes at harbours and auction halls.",
                "Fish transport vans and cold storage rooms.", "Fish markets checking the freshness of the catch."])]},
            {"h": "Advantages and limitations", "items": [("ul", [
                "Watches ice, meltwater and spoilage gases together for about Rs. 1,050.", "Owner sees it on any phone; no internet or app needed.",
                "Logs the whole voyage; simulator for demonstration and training.",
                "Limitation: the DHT11 cannot read below 0 °C; a DHT22 or DS18B20 would be more precise.",
                "Limitation: MQ sensors give relative readings and must be calibrated in clean air; the MQ-4 only gives yes / no here "
                "because the NodeMCU has a single analog input."])]},
            {"h": "Future improvements", "items": [("ul", [
                "Waterproof DS18B20 probe for exact ice temperature.", "An ADS1115 add-on to read both gas sensors as levels.",
                "GSM / LoRa link so the owner on shore gets alerts.", "Automatic drain pump when the meltwater is too high."])]},
            {"h": "Conclusion", "items": [("p",
                "The Marine Fish Quality Monitor turns a closed fish hold into something the owner can watch from a phone. It keeps a "
                "record of the voyage, raises a clear alarm when the ice runs out, the drain blocks or the fish start to spoil, and "
                "shows its readings honestly - helping fishermen land a fresher, more valuable catch.")]},
            {"h": "References", "items": [("ul", [
                "FAO - Ice in fisheries (Fisheries Technical Paper 331).", "Hanwei Electronics - MQ-135 and MQ-4 datasheets.",
                "Aosong - DHT11 datasheet.", "ESP8266 Arduino core documentation (ESP8266WebServer, LittleFS)."])]},
        ]}


def main():
    print("Building reports...")
    results, run_t = robotics_graphs()
    build(HERE / "Robotics_Project_Report_MarkerPilot.pdf", robotics_spec(results, run_t))
    build(HERE / "Electronics_Project_Report_HazardGuard_C3.pdf", electronics_spec())
    build(HERE / "IoT_Project_Report_Fish_Quality_Monitor.pdf", iot_spec(iot_graph()))


if __name__ == "__main__":
    main()
