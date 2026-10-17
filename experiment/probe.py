# lightweight noisy-neighbour probe: every 10 s, time a fixed CPU loop (~10 ms) and append to probe.csv
import time
f = open("/root/x/probe.csv", "a")
while True:
    t = time.perf_counter(); s = 0
    for i in range(200_000):
        s += i
    f.write(f"{time.time():.0f},{(time.perf_counter() - t) * 1e3:.2f}\n"); f.flush()
    time.sleep(10)
