#!/bin/bash
# Builds db_bench from RocksDB 9.8.4 exactly as used in the paper (Ubuntu 22.04).
# Note: without PORTABLE=1 the binary is tuned to the build machine's CPU; we built it on one of the AMD
# test machines and copied it to the others (all AMD Zen CPUs). Add PORTABLE=1 for a binary that runs anywhere.
set -e
apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential libgflags-dev \
  libsnappy-dev zlib1g-dev libbz2-dev liblz4-dev libzstd-dev wget
wget -q https://github.com/facebook/rocksdb/archive/refs/tags/v9.8.4.tar.gz && tar xzf v9.8.4.tar.gz
cd rocksdb-9.8.4 && make -j"$(nproc)" DEBUG_LEVEL=0 db_bench
strip -o ../db_bench db_bench && ../db_bench --version
