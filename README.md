# Prune, Don't Pick: Using Early Results Safely When Tuning LSM-Tree Key-Value Stores

Code and data for the paper by Abderrahmane Tahar, Ibtissam Abdesselam and Mohamed Aridj (Hassiba Benbouali University of Chlef), ICMSCT 2026.

**Summary.** RocksDB configurations look faster early in a run than they really are, and by different amounts. We ran 32 configurations from three sets for 30 minutes each with `db_bench`, three times on separate cloud machines, and repeated one set under workloads with 50% and 90% reads and with two-hour runs (17 runs in total). Choosing configurations by early throughput was unreliable. A conservative early-stopping rule was safe: stop a configuration once its running average falls below a fully measured result.

## Reproducing the paper's numbers

```bash
pip install numpy scipy matplotlib
python3 analysis/analyze.py    # prints Table 1 and all other numbers; writes analysis/results.json
python3 analysis/fig1.py       # writes fig1_crossing.pdf (Figure 1)
python3 analysis/revision.py   # workloads with reads and two-hour runs (Table 1, lower part)
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
| `experiment/revision/` | Workloads with reads (50% and 90% reads, `readrandomwriterandom`, 16 threads, Bloom filters, 4 GB block cache with direct reads) and two-hour runs; claims C5-C7 in the header of `run_rev.sh`. |
| `analysis/revision.py` | Results of the workloads with reads and the two-hour runs. |
| `data/revision/out_<workload>_rep<run>/` | Raw results, same format as below, plus `df.csv` (disk use per minute) and, for the repeated rw90 run, `diskprobe.csv`. |
| `data/revision/calibration_rw/` | The 3-minute calibration of the thread count for the workloads with reads (16 and 32 threads). |

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

## Workloads with reads and two-hour runs

grid8 was run three times with 50% reads (`out_rw50_rep1-3`), three times with 90% reads, and twice with two hours per configuration (`out_long_rep1-2`). `out_rw90_rep3` is excluded: its throughput declined steadily with run order regardless of configuration (a degrading disk). It was repeated as `out_rw90_rep4`, which the paper reports as run 3. The RocksDB `LOG` files of these runs (several GB) are not included.

## Running the experiment again

Each (set, run) needs one Linux machine with about 8 vCPUs, 16 GB of memory and 100 GB of local disk. With `db_bench` built by `experiment/build_db_bench.sh` and placed next to the scripts in `/root/x`:

```bash
bash setup_pod.sh grid8 1      # set = grid8 | pilot12 | speed12, run = 1..3
```

A run takes 4 h (grid8) or 6 h (12 configurations), plus about 10 minutes to build the base store. Results appear in `out_<set>_rep<run>/`; the probe is started separately with `python3 probe.py &`. We used RunPod containers (AMD EPYC 9575F, EPYC 4564P and Ryzen Threadripper 7960X CPUs); absolute throughput differs between machines, so compare configurations only within one run.

## License

Code: MIT License (see `LICENSE`). Data in `data/`: CC BY 4.0.
