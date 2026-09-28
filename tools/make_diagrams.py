import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagrams")
os.makedirs(OUT, exist_ok=True)
BLUE, AMBER, GREEN, GREY, RED = "#0f4c81", "#e08a00", "#1b7a43", "#eef1f5", "#b3261e"


def box(ax, x, y, w, h, text, fc="#fff", ec=BLUE, fs=9, bold=False, ls="-", tc="#1c2733"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=1.6, ls=ls))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, fontweight="bold" if bold else "normal", linespacing=1.3)


def arrow(ax, a, b, color=BLUE, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=14, color=color, lw=1.5, ls=ls, connectionstyle=f"arc3,rad={rad}"))


# ---------------- architecture
fig, ax = plt.subplots(figsize=(10, 6.4)); ax.set_xlim(0, 10); ax.set_ylim(0, 6.4); ax.axis("off")
ax.text(0.1, 6.15, "Land Stack — logical architecture", fontsize=13, fontweight="bold", color=BLUE)
for i, (t, c) in enumerate([("Citizen portal\n(PWA, 5 languages)", BLUE), ("Officer portal\n(Revenue · Registration\n· Planning)", BLUE), ("External systems\n(open REST API + OpenAPI)", GREEN)]):
    box(ax, 0.3 + i * 3.2, 5.0, 3.0, 0.85, t, fc=GREY, ec=c, fs=9, bold=True)
ax.text(0.3, 4.72, "Presentation & access", fontsize=8, color="#5b6b7b")
box(ax, 0.3, 3.5, 9.4, 1.1, "API layer — Flask blueprints: auth · parcels · deeds · governance · docs\nSession auth + citizen OTP · CSRF header guard · role & district authorisation\nSecurity headers · live OpenAPI specification", fc="#e8f1fb", fs=8.6, bold=True)
mods = ["State adapters\n(terms · units ·\ningestion maps)", "Geometry engine\n(area · validity ·\noverlap · jurisdiction)", "Deed workflow\n(OTP · duty ·\nregister · mutate)", "Risk model +\nrules\n(explainable)", "Satellite\nchange\ndetection", "Tamper-evident\naudit chain\n(SHA-256)"]
for i, m in enumerate(mods):
    box(ax, 0.3 + i * 1.58, 1.95, 1.48, 1.15, m, fc="#fff", ec=AMBER, fs=7.6)
ax.text(0.3, 3.22, "Domain services", fontsize=8, color="#5b6b7b")
box(ax, 0.3, 0.55, 4.6, 0.95, "Persistence (this prototype)\nSQLite · JSON documents\nappend-only audit table", fc=GREY, fs=8.6, bold=True)
box(ax, 5.1, 0.55, 4.6, 0.95, "Production path\nPostgreSQL + PostGIS\nrow-level security per district", fc="#fff", ec=GREEN, fs=8.6, bold=True, ls="--")
ax.text(0.3, 1.63, "Data", fontsize=8, color="#5b6b7b")
for x in (1.8, 5.0, 8.2): arrow(ax, (x, 5.0), (x, 4.55))
arrow(ax, (5.0, 3.55), (5.0, 3.1)); arrow(ax, (2.6, 1.95), (2.6, 1.5)); arrow(ax, (7.4, 1.95), (7.4, 1.5), color=GREEN, ls="--")
fig.savefig(os.path.join(OUT, "architecture.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

# ---------------- deed state machine
fig, ax = plt.subplots(figsize=(11, 3.9)); ax.set_xlim(0, 11); ax.set_ylim(0, 3.9); ax.axis("off")
ax.text(0.05, 3.65, "Sale-deed lifecycle", fontsize=13, fontweight="bold", color=BLUE)
xs = [0.1, 2.4, 4.7, 7.0, 9.3]
names = ["DRAFT", "AUTHENTICATED", "PAID", "REGISTERED", "MUTATED"]
W = 1.6
for name, x in zip(names, xs):
    end = name == "MUTATED"
    box(ax, x, 1.9, W, 0.75, name, fc="#dff3e7" if end else GREY, ec=GREEN if end else BLUE, fs=8.5, bold=True)
labels = ["seller + buyer\nOTP verified", "challan\nrecorded", "Registration\nOfficer registers", "Revenue Officer\nmutates the RoR"]
for i in range(4):
    x0, x1 = xs[i] + W, xs[i + 1]
    arrow(ax, (x0 + 0.03, 2.27), (x1 - 0.03, 2.27))
    ax.text((x0 + x1) / 2, 2.85, labels[i], ha="center", fontsize=7.4, color="#26384a")
box(ax, 2.6, 0.3, 4.2, 0.65, "CANCELLED  (allowed until REGISTERED)", fc="#fbe0de", ec=RED, fs=8, bold=True)
for src, dst in [(0.9, 3.3), (3.2, 4.7), (5.5, 6.1)]:
    arrow(ax, (src, 1.9), (dst, 0.97), color=RED, ls="--")
ax.text(7.1, 0.62, "Encumbered plots need a bank NOC before a deed\ncan be drafted. Until mutation, the plot shows a\n'mutation pending' marker, not a false mismatch.", fontsize=7.3, color="#5b6b7b", va="center")
fig.savefig(os.path.join(OUT, "deed_states.png"), dpi=170, bbox_inches="tight"); plt.close(fig)
print("diagrams ok")
