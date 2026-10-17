# Prune, Don't Pick: Using Early Results Safely When Tuning LSM-Tree Key-Value Stores

Code and data for the paper by Tahar Abderrahmane (Hassiba Benbouali University of Chlef), ICMSCT 2026.

**Summary.** RocksDB configurations look faster early in a run than they really are, and by different amounts. We ran 32 configurations from three sets for 30 minutes each with `db_bench`, three times on separate cloud machines (96 runs). Choosing configurations by early throughput was unreliable. A conservative early-stopping rule was safe: stop a configuration once its running average falls below a fully measured result.

## Reproducing the paper's numbers

```bash
pip install numpy scipy matplotlib
python3 analysis/analyze.py    # prints Table 1 and all other numbers; writes analysis/results.json
python3 analysis/fig1.py       # writes fig1_crossing.pdf (Figure 1)
```

The analysis takes about one minute and needs only the files in `data/`.

## Repository layout

| Path | Contents |
|---|---|
| `experiment/run_set.sh` | The experiment for one (set, run). Its header holds the protocol and the four claims, written before the first run. |
| `experiment/build_db_bench.sh` | Builds `db_bench` from RocksDB 9.8.4 as used in the paper. |
| `experiment/setup_pod.sh` | Installs runtime libraries on a fresh Ubuntu 22.04 machine and starts `run_set.sh`. |
| `experiment/probe.py` | Noisy-neighbour probe: times a fixed CPU loop every 10 s. |
| `experiment/configs_*.txt` | Configuration sets. Each line: background jobs, L0 slowdown trigger, write buffer size (MB). |
| `analysis/analyze.py` | Registered claims, Table 1, early-stopping replay, post-hoc analyses. |
| `analysis/fig1.py` | Figure 1. |
| `data/out_<set>_rep<run>/` | Raw results of one run (see below). |
| `data/calibration/` | The 3-minute calibration of the client thread count (4, 8, 16 threads). |

**Set names.** The directory names use the internal set names: `grid8` is grid8, `pilot12` is **rand12a** and `speed12` is **rand12b** in the paper.

## Files of one run (`data/out_<set>_rep<run>/`)

| File | Contents |
|---|---|
| `<config>.csv` | `db_bench` report: seconds elapsed, operations in the last 10 s interval (divide by 10 for ops/s). |
| `<config>.log` | Full `db_bench` output, including RocksDB statistics every 60 s and the cumulative stall percentage. |
| `order.txt` | Order in which the configurations ran (shuffled with seed 300 + run). |
| `progress.txt` | Completion time and summary line of each configuration. |
| `hw.txt`, `base.log`, `base_size.txt` | CPU model, memory limit, disk, and the build log and size of the 25 GB base store. |
| `probe.csv` | Unix time, duration of the probe loop in ms. |
| `run_*.log` | Console output of the script. |

Configuration names read `bg<jobs>_slow<slowdown trigger>_wb<write buffer>MB`. The stop trigger is `max(36, slowdown + 4)`.

## Running the experiment again

Each (set, run) needs one Linux machine with about 8 vCPUs, 16 GB of memory and 100 GB of local disk. With `db_bench` built by `experiment/build_db_bench.sh` and placed next to the scripts in `/root/x`:

```bash
bash setup_pod.sh grid8 1      # set = grid8 | pilot12 | speed12, run = 1..3
```

A run takes 4 h (grid8) or 6 h (12 configurations), plus about 10 minutes to build the base store. Results appear in `out_<set>_rep<run>/`; the probe is started separately with `python3 probe.py &`. We used RunPod containers (AMD EPYC 9575F, EPYC 4564P and Ryzen Threadripper 7960X CPUs); absolute throughput differs between machines, so compare configurations only within one run.

## License

Code: MIT License (see `LICENSE`). Data in `data/`: CC BY 4.0.
