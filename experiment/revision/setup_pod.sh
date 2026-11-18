#!/bin/bash
# usage: bash setup_pod.sh WORKLOAD REP DURATION -- installs runtime libs, starts the probe and run_rev.sh detached
set -e
cd "$(dirname "$0")"
apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libgflags2.2 libsnappy1v5 liblz4-1 libzstd1 libbz2-1.0 zlib1g libnuma1 python3 util-linux >/dev/null
chmod +x db_bench && ./db_bench --version
setsid nohup python3 probe.py > /dev/null 2>&1 < /dev/null &
setsid nohup bash run_rev.sh "$1" "$2" "$3" > run_$1_rep$2.log 2>&1 < /dev/null &
echo "started $1 rep $2 ($3 s)"
