"""Reproduces every number in the paper from the raw db_bench traces in ../data.

Registered claims (written into experiment/run_set.sh before the first run):
  M : S60 top-pick loss >= 15% in at least 2 of 3 sets (scores normalized per run, averaged over 3 runs).
  A : in every set, the true best is in the top 3 by averaged S60.   A5: same with S300.
  E : the UNC stopping rule stops the true best in <= 10% of tuning orders in every run.
Post-hoc analyses (designed after seeing the data, reported as exploratory): the screening variant,
the sensitivity check without the EPYC 4564P runs, and the running-average check.

Usage: python3 analysis/analyze.py      (prints a report and writes analysis/results.json)
Requires: numpy, scipy.
"""
import calendar, glob, json, os, re, time
import numpy as np
from scipy.stats import kendalltau

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SETS = {"grid8": "grid8", "pilot12": "rand12a", "speed12": "rand12b"}   # directory name -> name in the paper
SEG, NSEG = 30, 6            # replay: 6 segments of 300 s = 30 samples of 10 s
KEYS = ("S60", "S300", "full", "late")


# ---------------------------------------------------------------- loading
def block_ci(a, rng, block=6, nboot=2000):
    """95% CI of the mean of a 10 s series by moving-block bootstrap (blocks of 60 s)."""
    n = len(a)
    starts = rng.integers(0, n - block + 1, size=(nboot, -(-n // block)))
    means = [a[np.concatenate([np.arange(s, s + block) for s in row])[:n]].mean() for row in starts]
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def load_run(d, rng):
    probe = np.loadtxt(os.path.join(d, "probe.csv"), delimiter=",")
    med = np.median(probe[:, 1])
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "*.done"))):
        t = f[:-5]
        a = np.loadtxt(t + ".csv", delimiter=",", skiprows=1)[:, 1] / 10.0      # ops per second
        log = open(t + ".log").read()
        stall = float(re.findall(r"Cumulative stall:.*?([\d.]+) percent", log)[-1])
        t0 = calendar.timegm(time.strptime(re.search(r"Date:\s+(.+)", log).group(1).strip(), "%a %b %d %H:%M:%S %Y"))
        w = probe[(probe[:, 0] >= t0) & (probe[:, 0] < t0 + 1800), 1]
        out[os.path.basename(t)] = {"S60": a[:6].mean(), "S300": a[:30].mean(), "full": a.mean(), "late": a[30:].mean(),
                                    "stall_pct": stall, "disturbed_frac": float(np.mean(w > 2 * med)),
                                    "ci": block_ci(a, rng), "series": a}
    cpu = re.search(r"Model name:\s+(.+)", open(os.path.join(d, "hw.txt")).read()).group(1).strip()
    return out, cpu


# ---------------------------------------------------------------- scores and rules
def evaluate(sc, key):
    best = max(sc, key=lambda c: sc[c]["full"])
    order = sorted(sc, key=lambda c: -sc[c][key])
    return {"loss": float(1 - sc[order[0]]["full"] / sc[best]["full"]), "rank_of_best": order.index(best) + 1,
            "pick": order[0], "best": best}


def replay(curves, rule, rng, nperm=500, seg=SEG, nseg=NSEG):
    """Sequential tuning session replayed over random orders (Sect. 4.3).
    UNC : stop if mean-so-far * q95(full/partial ratios of completed configs) < incumbent (needs >= 3 completed).
    CONS: stop if mean-so-far < incumbent."""
    names = list(curves)
    full = {n: float(np.mean(curves[n])) for n in names}
    best = max(full, key=full.get)
    stopped_best = losses = saved = 0.0
    for _ in range(nperm):
        done, ratios, used = {}, {k: [] for k in range(1, nseg)}, 0
        for n in rng.permutation(names):
            c, stop = curves[n], False
            for k in range(1, nseg):
                part = float(np.mean(c[:k * seg]))
                if done:
                    inc = max(done.values())
                    if rule == "CONS":
                        hi = part
                    elif len(done) >= 3:
                        hi = part * float(np.quantile(ratios[k], 0.95))
                    else:
                        hi = np.inf
                    if hi < inc:
                        used, stop = used + k, True
                        break
            if not stop:
                used += nseg
                done[n] = full[n]
                for k in range(1, nseg):
                    ratios[k].append(full[n] / float(np.mean(c[:k * seg])))
            elif n == best:
                stopped_best += 1
        pick = max(done, key=done.get)
        losses += 1 - full[pick] / full[best]
        saved += 1 - used / (nseg * len(names))
    return {"p_best_stopped": stopped_best / nperm, "loss": losses / nperm, "time_saved": saved / nperm}


def screening(sc):
    """Post hoc (Sect. 4.4): run all configs for 60 s, then run them in order of S60 with CONS
    (S60 as first checkpoint, then every 300 s). Cost counts the 60 s screening of every config."""
    n, cost, done = len(sc), 60 * len(sc), {}
    for c in sorted(sc, key=lambda c: -sc[c]["S60"]):
        a, inc = sc[c]["series"], (max(done.values()) if done else None)
        if inc is not None and sc[c]["S60"] < inc:
            continue
        stopped = False
        for k in range(1, NSEG):
            if inc is not None and a[:SEG * k].mean() < inc:
                cost, stopped = cost + 300 * k, True
                break
        if not stopped:
            cost += 1800
            done[c] = sc[c]["full"]
    best = max(sc, key=lambda c: sc[c]["full"])
    pick = max(done, key=done.get)
    return {"time_saved": 1 - cost / (1800 * n), "loss": 1 - sc[pick]["full"] / sc[best]["full"], "full_runs": len(done)}


def averaged(runs, cs, keep):
    return {c: {k: float(np.mean([runs[r][c][k] / np.mean([runs[r][x][k] for x in cs]) for r in keep])) for k in KEYS}
            for c in cs}


def tau(x, y):
    return float(kendalltau(x, y)[0])


# ---------------------------------------------------------------- main
def main():
    rng = np.random.default_rng(0)
    res, allcfg = {}, []
    for dname, paper in SETS.items():
        runs, cpus = {}, {}
        for r in (1, 2, 3):
            runs[r], cpus[r] = load_run(os.path.join(DATA, f"out_{dname}_rep{r}"), rng)
        cs = sorted(runs[1])
        S = {"per_run": {}}
        for r, sc in runs.items():
            curves = {c: sc[c]["series"][:SEG * NSEG] for c in cs}
            allcfg += list(sc.values())
            S["per_run"][r] = {
                "cpu": cpus[r], "S60": evaluate(sc, "S60"), "S300": evaluate(sc, "S300"),
                "UNC": replay(curves, "UNC", np.random.default_rng(0)),
                "CONS": replay(curves, "CONS", np.random.default_rng(0)),
                "CONS_60s_checks": replay(curves, "CONS", np.random.default_rng(0), seg=6, nseg=30),
                "screen": screening(sc),
                "full_over_S60": [min(sc[c]["full"] / sc[c]["S60"] for c in cs), max(sc[c]["full"] / sc[c]["S60"] for c in cs)],
                "stall_pct": [min(sc[c]["stall_pct"] for c in cs), max(sc[c]["stall_pct"] for c in cs)],
                "max_disturbed": max(sc[c]["disturbed_frac"] for c in cs),
                "configs": {c: {k: v for k, v in sc[c].items() if k != "series"} for c in cs}}
        avg = averaged(runs, cs, (1, 2, 3))
        S["avg"] = {"S60": evaluate(avg, "S60"), "S300": evaluate(avg, "S300")}
        keep = [r for r in runs if "4564P" not in cpus[r]]
        avg2 = averaged(runs, cs, keep)
        S["without_4564P"] = {"runs": keep, "S60": evaluate(avg2, "S60"), "S300": evaluate(avg2, "S300")}
        S["tau_between_runs"] = {f"{a}-{b}": tau([runs[a][c]["full"] for c in cs], [runs[b][c]["full"] for c in cs])
                                 for a in runs for b in runs if a < b}
        res[paper] = S

    # running average vs final result, at the 300 s checkpoints, over all 96 runs
    res["min_running_avg_over_full"] = float(min(np.mean(c["series"][:SEG * k]) / c["full"] for c in allcfg for k in range(1, NSEG)))
    res["min_running_avg_over_full_1min"] = float(min(np.mean(c["series"][:6 * k]) / c["full"] for c in allcfg for k in range(1, 30)))
    res["min_S60_over_full"] = float(min(c["S60"] / c["full"] for c in allcfg))
    P = [p for s in SETS.values() for p in res[s]["per_run"].values()]
    res["claims"] = {
        "M": "PASS" if sum(res[s]["avg"]["S60"]["loss"] >= 0.15 for s in SETS.values()) >= 2 else "FAIL",
        "A": "PASS" if all(res[s]["avg"]["S60"]["rank_of_best"] <= 3 for s in SETS.values()) else "FAIL",
        "A5": "PASS" if all(res[s]["avg"]["S300"]["rank_of_best"] <= 3 for s in SETS.values()) else "FAIL",
        "E": "PASS" if all(p["UNC"]["p_best_stopped"] <= 0.10 for p in P) else "FAIL"}

    pct = lambda x: f"{100 * x:.0f}%"
    print(f"{'set':8s} run CPU                          S60loss rank60 rank300 | UNC stop/loss/saved | CONS stop/saved | CONS@60s stop/saved | screen saved (full runs)")
    for s in SETS.values():
        for r, p in res[s]["per_run"].items():
            print(f"{s:8s} {r}   {p['cpu'][:28]:28s} {pct(p['S60']['loss']):>6s} {p['S60']['rank_of_best']:6d} {p['S300']['rank_of_best']:7d} | "
                  f"{pct(p['UNC']['p_best_stopped']):>4s} / {100 * p['UNC']['loss']:.1f}% / {pct(p['UNC']['time_saved']):>4s} | {pct(p['CONS']['p_best_stopped']):>4s} / {pct(p['CONS']['time_saved']):>4s} | "
                  f"{pct(p['CONS_60s_checks']['p_best_stopped']):>4s} / {pct(p['CONS_60s_checks']['time_saved']):>4s} | "
                  f"{pct(p['screen']['time_saved']):>4s} ({p['screen']['full_runs']}), loss {pct(p['screen']['loss'])}")
        a, w = res[s]["avg"], res[s]["without_4564P"]
        print(f"{s:8s} avg  S60 loss {pct(a['S60']['loss'])}, rank of best: S60 {a['S60']['rank_of_best']}, S300 {a['S300']['rank_of_best']}"
              f" | without 4564P: S60 loss {pct(w['S60']['loss'])}, ranks {w['S60']['rank_of_best']}/{w['S300']['rank_of_best']}"
              f" | tau between runs {', '.join(f'{v:.2f}' for v in res[s]['tau_between_runs'].values())}")
    print(f"full/S60 range: {min(p['full_over_S60'][0] for p in P):.2f}-{max(p['full_over_S60'][1] for p in P):.2f};"
          f" stall: {min(p['stall_pct'][0] for p in P):.0f}-{max(p['stall_pct'][1] for p in P):.0f}%;"
          f" max disturbed: {pct(max(p['max_disturbed'] for p in P))};"
          f" min running avg/full at 300 s checkpoints: {res['min_running_avg_over_full']:.3f}, at 1-minute checkpoints:"
          f" {res['min_running_avg_over_full_1min']:.3f}; min S60/full: {res['min_S60_over_full']:.2f}")
    losses = [p["S60"]["loss"] for p in P]
    print(f"per-run S60 top-pick loss: median {pct(float(np.median(losses)))}, range {pct(min(losses))}-{pct(max(losses))},"
          f" wrong pick in {sum(p['S60']['pick'] != p['S60']['best'] for p in P)} of 9 runs, >=15% in {sum(l >= 0.15 for l in losses)}")
    print("CLAIMS", res["claims"])
    json.dump(res, open(os.path.join(ROOT, "analysis", "results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
