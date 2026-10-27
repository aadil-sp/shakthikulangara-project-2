"""Builds the three project reports (PDF) with their diagrams and graphs.

    python3 reports/build_reports.py

Needs: reportlab, matplotlib, numpy, opencv (robotics graphs run the real simulator).
Robotics graphs use real simulator runs of the MarkerPilot code; the electronics
graph replays the firmware's alarm logic; the IoT table holds readings logged
from the real board.
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
    """Replays the firmware's alarm logic on a simulated LPG leak."""
    warn, alarm, hold = 1200, 2100, 8
    t = [i * 0.25 for i in range(0, 361)]
    gas = []
    for s in t:
        g = 650 + 20 * math.sin(s)
        if 20 <= s < 50:
            g += (s - 20) / 30 * 2000
        elif 50 <= s < 60:
            g += 2000
        elif s >= 60:
            g += 2000 * math.exp(-(s - 60) / 6)
        gas.append(g)
    level, relay, hold_until = [], [], -1
    for s, g in zip(t, gas):
        lv = 2 if g >= alarm else 1 if g >= warn else 0
        if lv == 2:
            hold_until = s + hold
        level.append(lv)
        relay.append(1 if s < hold_until else 0)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.5, 4.0), dpi=170, sharex=True, gridspec_kw={"height_ratios": [3, 1.3]})
    a1.plot(t, gas, color="#ea580c", lw=2, label="gas sensor (ADC)")
    a1.axhline(warn, color="#eab308", ls="--", lw=1.2, label="warning 1200")
    a1.axhline(alarm, color="#dc2626", ls="--", lw=1.2, label="danger 2100")
    a1.set_ylabel("Gas reading (0-4095)")
    a1.legend(fontsize=7.5, loc="upper right")
    a1.grid(alpha=0.3)
    a1.set_title("Alarm logic replay: LPG leak, then window opened", fontsize=10, weight="bold")
    a2.step(t, level, color="#334155", where="post", label="alarm level (0 safe / 1 warn / 2 danger)")
    a2.step(t, [r * 2.2 for r in relay], color="#16a34a", where="post", lw=2, label="relay / exhaust fan")
    a2.set_yticks([0, 1, 2])
    a2.set_xlabel("Time (s)")
    a2.legend(fontsize=7, loc="upper right")
    a2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ASSETS / "electronics_response.png")
    plt.close(fig)


def iot_graph():
    """Readings logged from the real board (27 Oct 2026) against the thresholds."""
    logged = [(20, 714, 954, 350), (22, 712, 952, 341), (24, 684, 930, 347)]
    fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=170)
    names = ["MQ-3 alcohol", "MQ-5 LPG"]
    clean = [sum(r[1] for r in logged) / 3, sum(r[2] for r in logged) / 3]
    ax.barh(names, clean, color="#0f9488", label="clean room air (measured)")
    ax.axvline(1800, color="#d97706", ls="--", label="warning 1800 mV")
    ax.axvline(2800, color="#dc2626", ls="--", label="danger 2800 mV")
    for i, v in enumerate(clean):
        ax.text(v + 40, i, f"{v:.0f} mV", va="center", fontsize=8)
    ax.set_xlim(0, 3500)
    ax.set_xlabel("Sensor output (mV)")
    ax.set_title("Gas sensors in clean air vs alarm thresholds (real board)", fontsize=10, weight="bold")
    ax.legend(fontsize=7.5, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(ASSETS / "iot_readings.png")
    plt.close(fig)
    return logged


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
                f"let it slow down, steer around and back away from obstacles. In 300 randomised simulator tests the system reached "
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
                ["Wires, resistors", "1 kΩ + 2 kΩ per echo line", "1 set", "Echo voltage dividers, wiring", "Rs. 60"],
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
                           ["Buzzer", "GPIO 4", "Warning beep"],
                           ["Gateway (ESP32-C3)", "USB to laptop", "Serial 115200 baud: 'D,left,right' and 'T,l,f,r,v'"]],
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
                  ["MQ gas sensor", "DHT11 temp / humidity", "HC-SR04 ultrasonic", "Phone dashboard\n(settings)"],
                  ["Relay: fan / gas valve", "Buzzer", "Green / yellow / red LEDs", "TM1637 display", "WiFi hotspot\n192.168.4.1"],
                  "#fed7aa")
    flowchart(ASSETS / "electronics_flow.png", [
        ("Read gas (average of 8), distance, temperature", "end"), ("Gas sensor still warming up? (first 60 s)", "decision"),
        ("Compare with active profile thresholds", "step"), ("Danger? relay ON, red strobe, fast beep", "decision"),
        ("Warning? yellow blink, slow beep", "decision"), ("Safe: green LED", "step"),
        ("Relay stays on 8 s after danger clears", "step"), ("Update display + phone dashboard, repeat", "end")], "#fed7aa")
    electronics_graph()
    return {
        "title": "HazardGuard C3: Multi-Hazard Emergency and Safety Automation",
        "subtitle": "Gas leak, fire, danger-zone and tank-overflow protection with automatic exhaust / gas cut-off and a phone dashboard",
        "short": "HazardGuard C3 - multi-hazard safety controller", "category": "Electronics", "board": "ESP32-C3", "theme": "#c2410c",
        "sections": [
            {"h": "Abstract", "items": [("p",
                "HazardGuard C3 is a low-cost safety controller for kitchens, hotel boiler rooms and workshops. An MQ gas sensor "
                "detects LPG and smoke, a DHT11 measures temperature for fire and overheating, and an ultrasonic sensor watches a "
                "danger zone around a machine or the level in a tank. When something is dangerous, the ESP32-C3 switches on a relay "
                "(exhaust fan or gas shut-off valve), flashes a red LED, sounds a buzzer and shows a warning code on a 4-digit "
                "display. The controller also creates its own WiFi hotspot, so any phone can open a live dashboard at 192.168.4.1 "
                "to watch the readings, switch between Household, Hotel and Industrial profiles, change thresholds and silence the alarm.")]},
            {"h": "Aim of the project", "items": [("ul", [
                "Detect gas leaks, smoke, fire / overheating, danger-zone breaches and tank overflow with one controller.",
                "Act automatically: run an exhaust fan or close a gas valve through a relay.",
                "Warn people with LEDs, buzzer and a display, and on any phone without internet.",
                "Allow different safety limits for homes, hotels and factories, saved even after power cuts."])]},
            {"h": "Problem statement and need", "items": [("p",
                "LPG leaks and kitchen fires cause many accidents every year, often because nobody notices in time. Commercial "
                "gas alarms only beep - they do not ventilate the room or cut the gas - and they cannot be checked from another room. "
                "HazardGuard C3 reacts on its own within a fraction of a second and shows the situation on any phone nearby.")]},
            {"h": "Components used and cost", "items": [("table", [
                ["Component", "Model", "Qty", "Purpose", "Approx. cost"],
                ["Controller", "ESP32-C3 SuperMini", "1", "Reads sensors, runs logic, WiFi hotspot", "Rs. 300"],
                ["Gas sensor", "MQ-2 / MQ-135 module", "1", "LPG, methane and smoke", "Rs. 160"],
                ["Temperature sensor", "DHT11", "1", "Fire / overheating, humidity", "Rs. 110"],
                ["Ultrasonic sensor", "HC-SR04", "1", "Danger-zone breach and tank level", "Rs. 90"],
                ["Relay", "5 V 1-channel, opto-isolated", "1", "Switches exhaust fan or gas solenoid", "Rs. 70"],
                ["Display", "TM1637 4-digit", "1", "Readings and warning codes", "Rs. 90"],
                ["Buzzer", "5 V active buzzer", "1", "Audible alarm", "Rs. 20"],
                ["LEDs", "Green, yellow, red 5 mm", "3", "Safe / warning / danger", "Rs. 10"],
                ["Resistors", "3 x 220 Ω, 1 kΩ, 2 kΩ, 10 kΩ", "1 set", "LEDs, echo divider, DHT pull-up", "Rs. 15"],
                ["Power", "5 V 2 A USB-C adapter", "1", "Supply", "Rs. 150"],
                ["Total", "", "", "", "Rs. 1,015"]], [28, 40, 11, 68, 25], "Table 1: Bill of materials (approximate local prices)")]},
            {"h": "Circuit connections", "items": [
                ("table", [["Part pin", "ESP32-C3 pin", "Notes"],
                           ["MQ gas AO", "GPIO 1 (ADC)", "Through a 10k:10k divider if the module runs on 5 V"],
                           ["TM1637 CLK / DIO", "GPIO 2 / 3", ""],
                           ["HC-SR04 TRIG / ECHO", "GPIO 4 / 5", "ECHO through 1 kΩ / 2 kΩ divider"],
                           ["DHT11 DATA", "GPIO 6", "10 kΩ pull-up to 3.3 V"],
                           ["Buzzer", "GPIO 7", ""],
                           ["Relay IN", "GPIO 10", "Active LOW module"],
                           ["Green / yellow LED", "GPIO 0 / 8", "220 Ω to GND"],
                           ["Red LED", "GPIO 9", "3.3 V -> 220 Ω -> LED -> GPIO 9 (active LOW, safe for boot)"]],
                 [45, 35, 92], "Table 2: Wiring")]},
            {"h": "System overview", "items": [("img", ASSETS / "electronics_block.png", 165, "Figure 1: Block diagram")]},
            {"h": "How I did this (method)", "items": [
                ("p", "The gas reading is averaged over 8 samples to remove noise. For the first 60 seconds the MQ heater warms up, "
                      "so gas alarms are held back to avoid false alarms. Each profile has its own limits; the Industrial profile is the "
                      "most sensitive. If a sensor stops answering, the dashboard shows 'sensor fault' and the display shows E1 or E2 "
                      "instead of showing a made-up number."),
                ("p", "When danger is detected, the relay switches on and stays on for 8 seconds after the danger clears, so a fan does "
                      "not chatter on and off around the limit. The relay can also be forced on or off from the phone. Thresholds and "
                      "the chosen profile are stored in the ESP32's flash memory (Preferences), so they survive power cuts."),
                ("img", ASSETS / "electronics_flow.png", 90, "Figure 2: Control flow")]},
            {"h": "Testing and results", "items": [
                ("p", "Figure 3 replays the firmware's decision logic on a simulated LPG leak: the gas reading rises, crosses the warning "
                      "and danger limits, and falls after the window is opened. The relay switches on at the danger limit and switches "
                      "off 8 s after the reading drops back, exactly as designed."),
                ("img", ASSETS / "electronics_response.png", 160, "Figure 3: Alarm logic replay"),
                ("table", [["Test on the bench", "Expected result"],
                           ["Gas lighter (unlit) near MQ sensor", "Yellow, then red; relay ON; 'GAS' flashing"],
                           ["Hot air near DHT11 above 52 °C", "Red; 'FIrE' on display; relay ON"],
                           ["Hand within 30 cm of ultrasonic", "Danger-zone breach; 'ZonE' on display"],
                           ["Unplug the DHT11", "Dashboard shows 'Sensor fault'; display shows E1"],
                           ["Tap 'Silence buzzer' on phone", "Buzzer quiet for 2 minutes, lights keep flashing"]],
                 [75, 97], "Table 3: Bench test checklist")]},
            {"h": "Applications", "items": [("ul", [
                "Home kitchens: LPG leak alarm with automatic exhaust fan.",
                "Hotel kitchens and boiler rooms: overheating and gas protection.",
                "Workshops: keeping people out of a machine's danger zone.",
                "Tanks and sumps: overflow warning."])]},
            {"h": "Advantages and limitations", "items": [("ul", [
                "Acts automatically instead of only beeping.",
                "Works without internet: the phone connects straight to the device.",
                "Settings change from a phone and survive power cuts.",
                "Limitation: MQ sensors need warm-up and show relative values, not exact ppm.",
                "Limitation: the DHT11 reads the air, not flames directly; a flame sensor would react faster."])]},
            {"h": "Future improvements", "items": [("ul", [
                "Add a flame sensor and a CO sensor.", "Send SMS or app alerts through a home router.",
                "Battery backup so it keeps working during power cuts."])]},
            {"h": "Conclusion", "items": [("p",
                "HazardGuard C3 combines four kinds of hazard detection, automatic action and a phone dashboard in a controller that "
                "costs about a thousand rupees, showing that real safety automation can be cheap and simple.")]},
            {"h": "References", "items": [("ul", [
                "Hanwei Electronics - MQ-2 gas sensor datasheet.", "Aosong - DHT11 datasheet.",
                "Espressif - ESP32-C3 technical reference and Arduino core documentation."])]},
        ]}


def iot_spec(logged):
    block_diagram(ASSETS / "iot_block.png", "Multi-Hazard Monitor", "ESP32-C3\nhazard logic\n+ hotspot",
                  ["MQ-5 LPG gas", "MQ-3 alcohol vapour", "DHT11 temp / humidity", "Soil moisture probe", "HC-SR04 water level"],
                  ["Red alarm LED", "Open WiFi hotspot", "Live phone dashboard\n192.168.4.1", "JSON data /api/data"], "#99f6e4")
    flowchart(ASSETS / "iot_flow.png", [
        ("Read 5 sensors (16x oversampled analog)", "end"), ("Sensor missing? report 'not detected'", "decision"),
        ("Gas sensors warming up? (first 60 s)", "decision"), ("Compare each reading with its limits", "step"),
        ("Overall level = worst sensor", "step"), ("Red LED: off / slow blink / fast blink", "step"),
        ("Phones read /api/data every second", "end")], "#99f6e4")
    iot_graph()
    rows = [["Uptime", "MQ-3 (mV)", "MQ-5 (mV)", "Soil raw (mV)"]] + [[f"{r[0]} s", r[1], r[2], r[3]] for r in logged]
    return {
        "title": "Multi-Hazard Monitor: An IoT Safety Station with a Phone Dashboard",
        "subtitle": "LPG, alcohol vapour, temperature, soil saturation and water-level monitoring over a password-free WiFi hotspot",
        "short": "Multi-Hazard Monitor - IoT safety station", "category": "Internet of Things", "board": "ESP32-C3", "theme": "#0f766e",
        "sections": [
            {"h": "Abstract", "items": [("p",
                "The Multi-Hazard Monitor is an Internet-of-Things station that watches five different dangers at once: LPG / cooking "
                "gas leaks (MQ-5), alcohol or solvent vapour (MQ-3), high temperature (DHT11), soil that is too dry or so wet that "
                "flooding or landslides become likely (soil moisture probe), and rising water or an approaching object (ultrasonic). "
                "The ESP32-C3 creates its own open WiFi hotspot; any phone that joins it is taken straight to a live dashboard at "
                "192.168.4.1 that updates every second. A single red LED shows the overall state on the device itself. Sensors that "
                "are disconnected are clearly shown as 'not detected' instead of displaying fake values.")]},
            {"h": "Aim of the project", "items": [("ul", [
                "Monitor gas, vapour, temperature, soil moisture and water level with one low-cost board.",
                "Show live readings on any phone without internet or an app.",
                "Warn with a simple red LED: off, slow blink, fast blink.",
                "Be honest about faults: never show a made-up reading when a sensor is missing."])]},
            {"h": "Problem statement and need", "items": [("p",
                "Kerala faces LPG accidents at home and landslides and floods during the monsoon. Most monitoring systems watch only "
                "one danger and need internet or an app. A single cheap station that watches several dangers and can be read on any "
                "phone nearby is useful in homes, farms, schools and hillside settlements.")]},
            {"h": "Components used and cost", "items": [("table", [
                ["Component", "Model", "Qty", "Purpose", "Approx. cost"],
                ["Controller", "ESP32-C3 SuperMini", "1", "Reads sensors, hotspot, web server", "Rs. 300"],
                ["LPG sensor", "MQ-5 module", "1", "Cooking gas / natural gas leaks", "Rs. 150"],
                ["Alcohol sensor", "MQ-3 module", "1", "Alcohol, sanitiser and solvent vapour", "Rs. 150"],
                ["Temperature sensor", "DHT11", "1", "Temperature and humidity", "Rs. 110"],
                ["Soil sensor", "Soil moisture probe + module", "1", "Dry soil / waterlogged soil", "Rs. 80"],
                ["Ultrasonic sensor", "HC-SR04", "1", "Water level rise or object too close", "Rs. 90"],
                ["Indicator", "Red 5 mm LED + 220 Ω", "1", "Overall alarm state", "Rs. 5"],
                ["Resistors", "10 kΩ x4, 1 kΩ, 2 kΩ", "1 set", "MQ output dividers, echo divider", "Rs. 15"],
                ["Power", "5 V 2 A USB-C adapter", "1", "Supply (MQ heaters need 5 V)", "Rs. 150"],
                ["Total", "", "", "", "Rs. 1,050"]], [28, 40, 11, 68, 25], "Table 1: Bill of materials (approximate local prices)")]},
            {"h": "Circuit connections", "items": [
                ("p", "Analog sensors must use the ESP32-C3's ADC1 pins (GPIO 0-4) because ADC2 stops working while WiFi is on. "
                      "The ADC reads about 0-2.5 V reliably, so each 5 V MQ output goes through a 10 kΩ / 10 kΩ divider and the "
                      "firmware multiplies the reading back by 2."),
                ("table", [["Part pin", "ESP32-C3 pin", "Notes"],
                           ["MQ-3 AO", "GPIO 0", "10k:10k divider"], ["MQ-5 AO", "GPIO 1", "10k:10k divider"],
                           ["Soil AO", "GPIO 3", "Module powered from 3.3 V"], ["HC-SR04 TRIG / ECHO", "GPIO 4 / 5", "ECHO through 1 kΩ / 2 kΩ divider"],
                           ["DHT11 DATA", "GPIO 6", "10 kΩ pull-up"], ["Red LED", "GPIO 9", "3.3 V -> 220 Ω -> LED -> GPIO 9 (active LOW)"]],
                 [45, 35, 92], "Table 2: Wiring")]},
            {"h": "System overview", "items": [("img", ASSETS / "iot_block.png", 165, "Figure 1: Block diagram")]},
            {"h": "How I did this (method)", "items": [
                ("p", "Every analog sensor is read 16 times and averaged with the ESP32's calibrated millivolt function. The soil "
                      "reading is converted to a percentage using two calibration points (probe in dry air and dipped in water). "
                      "The DHT11 and ultrasonic sensor are marked missing after 3-4 failed readings in a row, and their cards on the "
                      "dashboard turn grey. The device runs only as a hotspot (no router), which keeps the WiFi channel fixed so phones "
                      "never lose the connection. A small DNS server makes phones open the dashboard automatically (captive portal)."),
                ("img", ASSETS / "iot_flow.png", 90, "Figure 2: Program flow")]},
            {"h": "Testing and results", "items": [
                ("p", "The firmware was flashed to the real ESP32-C3 and a laptop confirmed the open hotspot (signal -44 dBm, no "
                      "password). The serial log below was recorded from the board with the gas sensors in clean room air."),
                ("table", rows, [30, 40, 40, 40], "Table 3: Readings logged from the real board"),
                ("img", ASSETS / "iot_readings.png", 160, "Figure 3: Clean-air gas readings are far below the warning limits"),
                ("p", "In this first test the soil channel read about 345 mV, which the program treats as fully wet, and the DHT11 and "
                      "ultrasonic sensor were correctly reported as 'not detected' because they were not yet wired. This showed that the "
                      "fault reporting works: a missing sensor is never shown as a normal reading.")]},
            {"h": "Applications", "items": [("ul", [
                "Kitchens: LPG leak warning.", "Labs and workshops: solvent and alcohol vapour.",
                "Farms: irrigation reminder when soil is too dry.", "Hill areas: warning when soil is saturated during heavy rain.",
                "Sumps and drains: rising water alert."])]},
            {"h": "Advantages and limitations", "items": [("ul", [
                "Five hazards on one board for about a thousand rupees.", "Any phone can view it; no internet or app needed.",
                "Clear fault reporting.", "Limitation: MQ sensors give relative readings and need calibration in clean air.",
                "Limitation: an open hotspot can be joined by anyone nearby (it only shows readings)."])]},
            {"h": "Future improvements", "items": [("ul", [
                "Log history to an SD card or the cloud.", "Add a buzzer and SMS alerts.",
                "Solar power and a waterproof box for outdoor soil monitoring."])]},
            {"h": "Conclusion", "items": [("p",
                "The Multi-Hazard Monitor shows how one small IoT board can watch several everyday dangers at once and share them "
                "instantly with every phone nearby, while staying honest about what it can and cannot measure.")]},
            {"h": "References", "items": [("ul", [
                "Hanwei Electronics - MQ-3 and MQ-5 datasheets.", "Espressif - ESP32-C3 ADC calibration documentation.",
                "Arduino-ESP32 WebServer and DNSServer libraries."])]},
        ]}


def main():
    print("Building reports...")
    results, run_t = robotics_graphs()
    build(HERE / "Robotics_Project_Report_MarkerPilot.pdf", robotics_spec(results, run_t))
    build(HERE / "Electronics_Project_Report_HazardGuard_C3.pdf", electronics_spec())
    logged = iot_graph()
    build(HERE / "IoT_Project_Report_Multi_Hazard_Monitor.pdf", iot_spec(logged))


if __name__ == "__main__":
    main()
