#!/bin/bash
# ICMSCT'26 camera-ready: realistic db_bench replication. Usage: bash run_set.sh SET REP   (SET = grid8|pilot12|speed12)
#
# PRE-SPECIFIED (2026-10-16, before any run of this experiment; calibration used only 2 configs x 3 min):
#   Platform: RunPod Compute-Optimized pods (8 vCPU, 16 GB RAM limit, Ubuntu 22.04, 100 GB local container disk);
#             each (set, repetition) runs entirely on one pod; CPU model is logged.
#   Tool: db_bench (RocksDB 9.8.4, release build). Keys 20 B, values 400 B, lz4 compression, WAL on, no sync.
#   Base DB: fillrandom of 180M keys (1 thread, auto-compaction and WAL off), then full compaction (~25 GB, > RAM).
#             Every config starts from an identical copy of this base (SST files hard-linked, metadata copied).
#   Run: overwrite (random keys over the same 180M key space), 4 client threads (calibrated), closed loop,
#        1800 s, throughput reported every 10 s; the config sets max_background_jobs, level0_slowdown_writes_trigger
#        (stop trigger max(36, slow+4)) and write_buffer_size; all other options are RocksDB defaults.
#        Config order shuffled with seed 300+REP.
#   Truth = mean throughput over 1800 s. Short scores: S60 = mean of first 60 s; S300 = first 300 s.
#   CLAIM M  (misranking): S60 top-pick loss >= 15% in at least 2 of 3 sets (scores averaged over 3 reps,
#            each rep normalized by its own mean).
#   CLAIM A  (shortlist): in every set, the true best is in the top 3 by S60.   CLAIM A5: same with S300.
#   CLAIM E  (ESTune-style replay, icm_replay.py with 6 segments of 300 s): the uncertainty rule stops the
#            true best in <= 10% of permutations in every (set, rep).
#   Also reported: stall percentages per run, per-rep results, truth over 300-1800 s, run-to-run tau.
set -e
ulimit -n $(ulimit -Hn)
trap 'echo "FAILED at line $LINENO (exit $?)" >> $OUT/progress.txt' ERR
SET=$1; REP=$2
cd "$(dirname "$0")"; HERE=$(pwd)
B=$HERE/db_bench
OUT=$HERE/out_${SET}_rep${REP}; mkdir -p $OUT
COMMON="--key_size=20 --value_size=400 --compression_type=lz4 --num=180000000"
{ lscpu | grep -E 'Model name|^CPU\(s\)'; nproc; cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null; df -h $HERE | tail -1; } > $OUT/hw.txt
DB=$HERE/db; mkdir -p $DB
if [ ! -f $DB/base.ok ]; then
  rm -rf $DB/base
  $B --benchmarks=fillrandom,compact --db=$DB/base $COMMON --threads=1 --disable_auto_compactions=1 --disable_wal=1 --max_background_jobs=8 --subcompactions=8 > $OUT/base.log 2>&1
  touch $DB/base.ok
fi
du -sh $DB/base > $OUT/base_size.txt
python3 -c "import random,sys; l=open('configs_$SET.txt').read().split('\n'); l=[x for x in l if x]; random.Random(300+$REP).shuffle(l); print('\n'.join(l))" > $OUT/order.txt
while read b s w; do
  tag=bg${b}_slow${s}_wb${w}MB
  [ -f $OUT/$tag.done ] && continue
  st=$(( s+4 > 36 ? s+4 : 36 ))
  rm -rf $DB/run && mkdir $DB/run
  for f in $DB/base/*; do case $f in *.sst) ln $f $DB/run/;; *) cp $f $DB/run/;; esac; done
  $B --benchmarks=overwrite,stats --use_existing_db=1 --db=$DB/run $COMMON --threads=4 --duration=1800 \
     --max_background_jobs=$b --level0_slowdown_writes_trigger=$s --level0_stop_writes_trigger=$st \
     --write_buffer_size=$((w<<20)) --report_interval_seconds=10 --report_file=$OUT/$tag.csv \
     --statistics=1 --stats_interval_seconds=60 --stats_per_interval=1 --sync=0 > $OUT/$tag.log 2>&1
  du -sh $DB/run >> $OUT/$tag.log
  rm -rf $DB/run
  touch $OUT/$tag.done
  echo "$(date +%H:%M) $tag $(grep -m1 '^overwrite' $OUT/$tag.log | cut -c1-120)" >> $OUT/progress.txt
done < $OUT/order.txt
echo ALLDONE >> $OUT/progress.txt
