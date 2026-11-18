"""Workloads with reads (rw50, rw90; grid8, 30 min). Reuses the functions of analyze.py.
rw90 run 3 (out_rw90_rep3) is excluded: its throughput declined with run order on a degrading disk; it was repeated as out_rw90_rep4,
which the paper reports as run 3. Usage: python3 analysis/revision.py"""
import sys, os, re, glob, json, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze as A
from scipy.stats import kendalltau
R = os.path.join(os.path.dirname(HERE), "data", "revision")
rng = np.random.default_rng(0)
out = {}
for w in ("rw50", "rw90"):
    res = {}
    for r in ((1, 2, 3) if w == "rw50" else (1, 2, 4)):
        sc, cpu = A.load_run(os.path.join(R, f"out_{w}_rep{r}"), rng)
        cs = sorted(sc); curves = {c: sc[c]["series"][:180] for c in cs}
        p = {"cpu": cpu.split()[2], "S60": A.evaluate(sc, "S60"), "S300": A.evaluate(sc, "S300"),
             "CONS": A.replay(curves, "CONS", np.random.default_rng(0)),
             "CONS60": A.replay(curves, "CONS", np.random.default_rng(0), seg=6, nseg=30),
             "UNC": A.replay(curves, "UNC", np.random.default_rng(0)),
             "screen": A.screening(sc),
             "minRA5": min(np.mean(sc[c]["series"][:30 * k]) / sc[c]["full"] for c in cs for k in range(1, 6)),
             "minRA1": min(np.mean(sc[c]["series"][:6 * k]) / sc[c]["full"] for c in cs for k in range(1, 30)),
             "S60_over_full": [min(sc[c]["S60"] / sc[c]["full"] for c in cs), max(sc[c]["S60"] / sc[c]["full"] for c in cs)],
             "spread": max(sc[c]["full"] for c in cs) / min(sc[c]["full"] for c in cs) - 1,
             "stall": [min(sc[c]["stall_pct"] for c in cs), max(sc[c]["stall_pct"] for c in cs)],
             "disturbed": max(sc[c]["disturbed_frac"] for c in cs),
             "full": {c: sc[c]["full"] for c in cs}, "S60v": {c: sc[c]["S60"] for c in cs}}
        res[r] = p
    out[w] = res
pct = lambda x: f"{100*x:.0f}%"
for w, res in out.items():
    print(f"== {w}")
    for r, p in res.items():
        print(f" run{r} {p['cpu']:6s} S60 loss {pct(p['S60']['loss']):>4s} rank {p['S60']['rank_of_best']} | S300 loss {pct(p['S300']['loss'])} rank {p['S300']['rank_of_best']}"
              f" | CONS stop {pct(p['CONS']['p_best_stopped'])} saved {pct(p['CONS']['time_saved'])} | CONS60 stop {pct(p['CONS60']['p_best_stopped'])} saved {pct(p['CONS60']['time_saved'])}"
              f" | UNC stop {pct(p['UNC']['p_best_stopped'])} loss {100*p['UNC']['loss']:.1f}% saved {pct(p['UNC']['time_saved'])}"
              f" | screen saved {pct(p['screen']['time_saved'])} loss {pct(p['screen']['loss'])}"
              f" | minRA5 {p['minRA5']:.3f} minRA1 {p['minRA1']:.3f} S60/full {p['S60_over_full'][0]:.2f}-{p['S60_over_full'][1]:.2f}"
              f" spread {pct(p['spread'])} stall {p['stall'][0]:.0f}-{p['stall'][1]:.0f}% dist {pct(p['disturbed'])}")
    rr = sorted(res)
    for a, b in ((rr[0], rr[1]), (rr[0], rr[2]), (rr[1], rr[2])):
        cs = sorted(res[a]["full"]); print(f"  tau run{a}-run{b}: {kendalltau([res[a]['full'][c] for c in cs], [res[b]['full'][c] for c in cs])[0]:.2f}", end="")
    print()
runs = [p for w in out for p in out[w].values()]
print("C5 (rw part): CONS stops best in 0% of orders in every rw run:", all(p["CONS"]["p_best_stopped"] == 0 for p in runs))
print("C6: S60 loss >= 10% in at least 3 of 6 rw runs:", sum(p["S60"]["loss"] >= 0.10 for p in runs), "of 6 ->", sum(p["S60"]["loss"] >= 0.10 for p in runs) >= 3)
json.dump({w: {r: {k: v for k, v in p.items()} for r, p in res.items()} for w, res in out.items()}, open(os.path.join(HERE, "revision_rw_results.json"), "w"), indent=1, default=float)


# ---------------------------------------------------------------- two-hour runs

def screen_long(sc, nseg=23, seg=30):
    """Screening variant (analyze.screening) for runs of nseg*seg samples."""
    n, T = len(sc), nseg * seg * 10; cost, done = 60 * n, {}
    for c in sorted(sc, key=lambda c: -sc[c]["S60"]):
        a, inc = sc[c]["series"], (max(done.values()) if done else None)
        if inc is not None and sc[c]["S60"] < inc:
            continue
        stopped = False
        for k in range(1, nseg):
            if inc is not None and a[:seg * k].mean() < inc:
                cost, stopped = cost + seg * 10 * k, True
                break
        if not stopped:
            cost += T; done[c] = sc[c]["full"]
    best = max(sc, key=lambda c: sc[c]["full"]); pick = max(done, key=done.get)
    return {"time_saved": 1 - cost / (T * n), "loss": 1 - sc[pick]["full"] / sc[best]["full"], "full_runs": len(done)}

N = 719
out = {}  # two-hour runs (overwrite, 7200 s): truth = 7200 s mean over the 719 samples common to all configs
for r in (1, 2):
    d = f"{R}/out_long_rep{r}"
    sc = {}
    for f in sorted(glob.glob(d + "/bg*.csv")):
        a = np.loadtxt(f, delimiter=",", skiprows=1)[:N, 1] / 10.0
        sc[os.path.basename(f)[:-4]] = {"S60": a[:6].mean(), "S300": a[:30].mean(), "m30": a[:180].mean(), "full": a.mean(), "series": a,
                                       "stall": float(re.findall(r"Cumulative stall:.*?([\d.]+) percent", open(f[:-4] + ".log").read())[-1])}
    cs = sorted(sc); best = max(cs, key=lambda c: sc[c]["full"]); top30 = max(cs, key=lambda c: sc[c]["m30"])
    curves = {c: sc[c]["series"] for c in cs}
    p = {"best_2h": best, "best_30min": top30, "C7": best == top30,
         "loss_pick_by_30min": 1 - sc[top30]["full"] / sc[best]["full"],
         "tau_30min_2h": kendalltau([sc[c]["m30"] for c in cs], [sc[c]["full"] for c in cs])[0],
         "S60": A.evaluate(sc, "S60"), "S300": A.evaluate(sc, "S300"),
         "CONS": A.replay(curves, "CONS", np.random.default_rng(0), seg=30, nseg=23),
         "CONS60": A.replay(curves, "CONS", np.random.default_rng(0), seg=6, nseg=119),
         "UNC": A.replay(curves, "UNC", np.random.default_rng(0), seg=30, nseg=23),
         "screen": screen_long(sc),
         "minRA5": min(sc[c]["series"][:30 * k].mean() / sc[c]["full"] for c in cs for k in range(1, 24)),
         "minRA1": min(sc[c]["series"][:6 * k].mean() / sc[c]["full"] for c in cs for k in range(1, 119)),
         "drop_30_to_2h": [min(1 - sc[c]["full"] / sc[c]["m30"] for c in cs), max(1 - sc[c]["full"] / sc[c]["m30"] for c in cs)],
         "table": {c: [round(sc[c]["S60"] / 1e3), round(sc[c]["m30"] / 1e3), round(sc[c]["full"] / 1e3), sc[c]["stall"]] for c in cs}}
    out[r] = p
    pct = lambda x: f"{100*x:.0f}%"
    print(f"== long run {r}: best 2h {best}, best 30min {top30} -> C7 {'PASS' if p['C7'] else 'FAIL'}; loss picking by 30 min {pct(p['loss_pick_by_30min'])}; tau(30min,2h) {p['tau_30min_2h']:.2f}")
    print(f"   S60 loss {pct(p['S60']['loss'])} rank {p['S60']['rank_of_best']} | S300 loss {pct(p['S300']['loss'])} rank {p['S300']['rank_of_best']}")
    print(f"   CONS stop {pct(p['CONS']['p_best_stopped'])} saved {pct(p['CONS']['time_saved'])} | CONS60 stop {pct(p['CONS60']['p_best_stopped'])} saved {pct(p['CONS60']['time_saved'])} | UNC stop {pct(p['UNC']['p_best_stopped'])} loss {100*p['UNC']['loss']:.1f}% saved {pct(p['UNC']['time_saved'])}")
    print(f"   screen saved {pct(p['screen']['time_saved'])} loss {pct(p['screen']['loss'])} full runs {p['screen']['full_runs']}")
    print(f"   minRA5 {p['minRA5']:.3f} minRA1 {p['minRA1']:.3f}; drop 30min->2h {pct(p['drop_30_to_2h'][0])}-{pct(p['drop_30_to_2h'][1])}")
    for c, v in sorted(p["table"].items(), key=lambda kv: -kv[1][2]): print(f"     {c:20s} S60 {v[0]:4d}k 30min {v[1]:4d}k 2h {v[2]:4d}k stall {v[3]:.0f}%")
json.dump(out, open(os.path.join(HERE, "revision_long_results.json"), "w"), indent=1, default=float)
