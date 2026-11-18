#!/bin/bash
# Calibration for the mixed workloads: bloom-filter base, then 3-minute runs of two extreme grid8 configs at 16 and 32 threads.
ulimit -n $(ulimit -Hn)
cd /root/x; B=./db_bench; D=/root/x/cdb; O=/root/x/calib; mkdir -p $O $D
C="--key_size=20 --value_size=400 --compression_type=lz4 --num=180000000 --bloom_bits=10"
pkill -f "bash run_rev.sh" ; pkill db_bench; sleep 2; rm -rf /root/x/db
$B --benchmarks=fillrandom,compact --db=$D/base $C --threads=1 --disable_auto_compactions=1 --disable_wal=1 --max_background_jobs=8 --subcompactions=8 > $O/base.log 2>&1
for rw in 50 90; do for t in 16 32; do for cfg in "1 36 256" "4 8 32"; do set -- $cfg
  rm -rf $D/run; mkdir $D/run; for f in $D/base/*; do case $f in *.sst) ln $f $D/run/;; *) cp $f $D/run/;; esac; done
  tag=rw${rw}_t${t}_bg$1_s$2_wb$3
  $B --benchmarks=readrandomwriterandom,stats --readwritepercent=$rw --use_direct_reads=1 --cache_size=4294967296 --use_existing_db=1 --db=$D/run $C \
     --threads=$t --duration=180 --max_background_jobs=$1 --level0_slowdown_writes_trigger=$2 --level0_stop_writes_trigger=$(( $2+4>36?$2+4:36 )) \
     --write_buffer_size=$(($3<<20)) --report_interval_seconds=10 --report_file=$O/$tag.csv --statistics=1 --sync=0 > $O/$tag.log 2>&1
  echo "$tag $(grep -m1 '^readrandomwriterandom' $O/$tag.log | cut -c1-160) | $(grep 'Cumulative stall' $O/$tag.log | tail -1 | cut -c1-60)" >> $O/summary.txt
done; done; done
echo CALIBDONE >> $O/summary.txt
