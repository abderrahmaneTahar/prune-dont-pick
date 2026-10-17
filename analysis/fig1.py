"""Figure 1 of the paper: two grid8 configurations from run 2. Usage: python3 analysis/fig1.py  (writes fig1_crossing.pdf)"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = os.path.join(ROOT, "data", "out_grid8_rep2")
fig, ax = plt.subplots(figsize=(6.2, 2.6))
for c, lab, col in (("bg4_slow36_wb256MB", "A: 4 jobs, slowdown 36, 256 MB buffer", "tab:red"),
                    ("bg4_slow8_wb32MB", "B: 4 jobs, slowdown 8, 32 MB buffer", "tab:blue")):
    a = np.loadtxt(os.path.join(d, c + ".csv"), delimiter=",", skiprows=1)[:, 1] / 10 / 1e3
    t = np.arange(1, len(a) + 1) * 10 / 60
    ax.plot(t, a, color=col, lw=0.6, alpha=0.35)
    ax.plot(t, np.cumsum(a) / np.arange(1, len(a) + 1), color=col, lw=2, label=lab)
ax.axvline(1, color="gray", ls=":", lw=1)
ax.text(1.3, 520, "1 min", color="gray", fontsize=8)
ax.set_xlabel("time (minutes)")
ax.set_ylabel("throughput (k ops/s)")
ax.set_xlim(0, 30)
ax.set_ylim(0, 600)
ax.legend(fontsize=7.5, frameon=False, loc="upper right")
fig.tight_layout()
fig.savefig(os.path.join(ROOT, "fig1_crossing.pdf"))
