#!/bin/bash
# ICMSCT'26 revision experiment. Usage: bash run_rev.sh WORKLOAD REP DURATION
#   WORKLOAD = rw50 (readrandomwriterandom, 50% reads) | rw90 (90% reads) | long (overwrite, as in the paper)
#
# PRE-SPECIFIED (2026-11-15, before any run of this experiment). Same platform, tool, base DB, key/value sizes,
# 4 client threads, config set grid8 and replay as the paper (run_set.sh); only the benchmark and duration change.
#   rw50 / rw90: readrandomwriterandom --readwritepercent=50 / 90, uniform keys, 1800 s; 3 runs each on separate pods.
#   long: overwrite, 7200 s per config; 2 runs on separate pods. Truth for long = mean over 7200 s.
#   rw50/rw90 use direct reads with a 4 GB block cache, so every config starts with a cold cache (each run is a new
#   process) and the OS page cache, shared through hard-linked files, cannot favour later configs.
#   Throughput = all operations (reads + writes) per second. Config order shuffled with seed 400+REP.
#   CLAIM C5 (safety): CONS (stop if running average < incumbent, checks every 300 s) stops the true best in
#            0 of 500 replayed orders in every run of rw50, rw90 and long.
#   CLAIM C6 (misranking under mixed load): the per-run S60 top-pick loss is >= 10% in at least 3 of the 6 rw50/rw90 runs.
#   CLAIM C7 (30 min vs 2 h): in both long runs, the configuration with the best 1800 s mean is also the best by 7200 s mean.
#   REVISED 2026-11-15 22:50 (before any long result): long rebuilds the base (fixed seed 42) before each config and
#   moves it into place, because keeping the base copy filled the disk; df is logged every 60 s.
#   REVISED 2026-11-15 23:40 (before any rw result is used; the first rw attempt with 4 threads and no Bloom filters is
#   discarded): an independent audit and the live logs showed that 4 threads with direct reads were read-latency bound
#   (40-60k ops/s, 0.0% stalls in all 6 runs), so the knobs could not matter. rw50/rw90 now use Bloom filters
#   (--bloom_bits=10, also in their base) and 16 client threads. Calibration (calib_rw.sh, bg1_s36_wb256 vs bg4_s8_wb32,
#   180 s): 16 threads gives 0.1% vs 11% stalls (rw50) and 0% vs 30% (rw90); 32 threads adds nothing for rw50.
#   Same rule as the paper's calibration: a load at which configurations differ in stalls. long is unchanged.
#   REVISED 2026-11-16 07:15: rw90 run 3 (pod 8) slowed down monotonically with run order (375k -> 109k ops/s) while
#   the CPU probe was undisturbed, i.e. the disk degraded; it is rerun as REP=4 on a new pod, with a disk probe
#   (64 MB O_DIRECT read every 60 s -> diskprobe.csv). The degraded run is kept and reported as excluded.
#   Also reported: min over configs and checkpoints of running average / full-run mean (values > 1 mean a rise later),
#   stall %, disk model and a 1 GB direct-write speed test.
set -e
ulimit -n $(ulimit -Hn)
W=$1; REP=$2; DUR=$3
cd "$(dirname "$0")"; HERE=$(pwd)
B=$HERE/db_bench
OUT=$HERE/out_${W}_rep${REP}; mkdir -p $OUT
trap 'echo "FAILED at line $LINENO (exit $?)" >> $OUT/progress.txt' ERR
COMMON="--key_size=20 --value_size=400 --compression_type=lz4 --num=180000000"
T=4
case $W in rw50|rw90) COMMON="$COMMON --bloom_bits=10"; T=16;; esac
case $W in
  rw50) BENCH="readrandomwriterandom --readwritepercent=50 --use_direct_reads=1 --cache_size=4294967296";;
  rw90) BENCH="readrandomwriterandom --readwritepercent=90 --use_direct_reads=1 --cache_size=4294967296";;
  long) BENCH="overwrite ";;
esac
{ lscpu | grep -E 'Model name|^CPU\(s\)'; nproc; cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || true; df -h $HERE | tail -1;
  lsblk -d -o NAME,ROTA,MODEL,SIZE 2>/dev/null || true; findmnt -T $HERE 2>/dev/null | tail -1 || true; cat /proc/sys/kernel/random/boot_id;
  dd if=/dev/zero of=$HERE/ddtest bs=1M count=1024 oflag=direct 2>&1 | tail -1; rm -f $HERE/ddtest; true; } > $OUT/hw.txt
DB=$HERE/db; mkdir -p $DB
build_base() {
  rm -rf $DB/base
  $B --benchmarks=fillrandom,compact --db=$DB/base $COMMON --seed=42 --threads=1 --disable_auto_compactions=1 --disable_wal=1 --max_background_jobs=8 --subcompactions=8 >> $OUT/base.log 2>&1
  touch $DB/base.ok
}
dd if=/dev/urandom of=$HERE/diskprobe bs=1M count=256 2>/dev/null || true
( while sleep 60; do echo "$(date +%s),$(df -B1 --output=used $HERE | tail -1)" >> $OUT/df.csv
    a=$(date +%s.%N); dd if=$HERE/diskprobe of=/dev/null bs=1M count=64 iflag=direct 2>/dev/null; b=$(date +%s.%N)
    echo "$(date +%s),$(echo "$b - $a" | bc 2>/dev/null || python3 -c "print($b-$a)")" >> $OUT/diskprobe.csv; done ) &
DFPID=$!
[ -f $DB/base.ok ] || build_base
du -sh $DB/base > $OUT/base_size.txt
python3 -c "import random; l=[x for x in open('configs_grid8.txt').read().split('\n') if x]; random.Random(400+$REP).shuffle(l); print('\n'.join(l))" > $OUT/order.txt
while read b s w; do
  tag=bg${b}_slow${s}_wb${w}MB
  [ -f $OUT/$tag.done ] && continue
  st=$(( s+4 > 36 ? s+4 : 36 ))
  rm -rf $DB/run
  if [ "$W" = long ]; then [ -f $DB/base.ok ] || build_base; mv $DB/base $DB/run; rm -f $DB/base.ok
  else mkdir $DB/run; for f in $DB/base/*; do case $f in *.sst) ln $f $DB/run/;; *) cp $f $DB/run/;; esac; done; fi
  $B --benchmarks=${BENCH%% *},stats ${BENCH#* } --use_existing_db=1 --db=$DB/run $COMMON --threads=$T --duration=$DUR \
     --max_background_jobs=$b --level0_slowdown_writes_trigger=$s --level0_stop_writes_trigger=$st \
     --write_buffer_size=$((w<<20)) --report_interval_seconds=10 --report_file=$OUT/$tag.csv \
     --statistics=1 --stats_interval_seconds=60 --stats_per_interval=1 --sync=0 > $OUT/$tag.log 2>&1
  du -sh $DB/run >> $OUT/$tag.log
  cp $DB/run/LOG $OUT/$tag.rocksdb_LOG 2>/dev/null || true
  rm -rf $DB/run
  touch $OUT/$tag.done
  echo "$(date +%H:%M) $tag $(grep -m1 -E '^(overwrite|readrandomwriterandom)' $OUT/$tag.log | cut -c1-120)" >> $OUT/progress.txt
done < $OUT/order.txt
kill $DFPID 2>/dev/null || true
echo ALLDONE >> $OUT/progress.txt
