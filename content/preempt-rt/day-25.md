---
title: "Day 25: Latency Histograms: Interpreting cyclictest Output"
date: 2026-07-07
tags: ["til", "preempt-rt", "histogram", "latency", "analysis"]
---

## What I Explored Today

Today I dug into the histogram output from cyclictest, moving beyond just looking at max latency numbers. While a single max-latency value tells you if you passed or failed a test, the histogram reveals the *distribution* of latencies — showing you where your system spends most of its time, whether you have pathological outliers, and how consistent your real-time performance actually is. I ran controlled tests on a PREEMPT_RT kernel and learned to read the histogram columns, spot bimodal distributions, and correlate spikes with specific kernel activity.

## The Core Concept

A cyclictest histogram is a frequency table: for each measured latency value (in microseconds), it records how many timer wakeups experienced exactly that latency. The output typically shows latency buckets from 0 up to some maximum, with cumulative counts.

Why does this matter? A single max-latency number can be misleading. A system that hits 150 µs once in a million samples might look worse than one that hits 100 µs regularly — but the first system is actually more deterministic. The histogram tells you:

- **Mode**: Where most samples cluster (your typical latency)
- **Tail behavior**: How quickly the distribution drops off after the mode
- **Outliers**: Isolated spikes vs. sustained high-latency regions
- **Bimodality**: Two distinct peaks often indicate a periodic interference source (e.g., a timer tick or RCU callback)

For production systems, you care about both the worst-case latency and the *jitter* — the spread between your typical and worst-case latencies. A tight histogram with a long tail is often more acceptable than a wide, flat distribution.

## Key Commands / Configuration / Code

### Basic Histogram Collection

```bash
# Run cyclictest for 60 seconds on CPU 1, with 1 µs resolution histogram
# -h 200: histogram buckets from 0 to 200 µs
# -i 1000: interval of 1000 µs (1 ms)
# -p 99: priority 99 (FIFO)
# -a 1: affine to CPU 1
# -q: quiet mode (only print summary)
sudo cyclictest -h 200 -i 1000 -p 99 -a 1 -q -D 60s
```

### Interpreting the Output

```
# /dev/cpu_dma_latency set to 0us
policy: fifo: loadavg: 0.00 0.01 0.05 1/143 12345

T: 0 (12345) P: 99 I:1000 C:   60000 Min:      2 Act:    3 Avg:    4 Max:     27
# Histogram
000000 0001 0002 0003 0004 0005 0006 0007 0008 0009 0010
--------------------------------------------------------
000000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000
000010 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000
000020 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000
000030 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000
...
# Histogram Overflows: 0
# Histogram Total: 60000
```

The histogram lines show latency ranges. The first column is the lower bound of the bucket (in µs). Each subsequent column is a 1 µs bucket. For example:

```
000010 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000
```

This row covers latencies from 10 µs to 19 µs. Each of the 10 columns represents 1 µs — so column 2 is 11 µs, column 3 is 12 µs, etc. The values are counts of samples that fell into that exact latency.

### Better Visualization with `--histofall`

```bash
# Use histofall to get per-CPU histograms merged
sudo cyclictest -h 200 -i 1000 -p 99 -a 2 -q -D 60s --histofall=2
```

This outputs a single histogram for CPU 2, which is easier to parse programmatically.

### Parsing with Python

```python
#!/usr/bin/env python3
import sys

def parse_histogram(filepath):
    with open(filepath) as f:
        lines = f.readlines()
    
    # Find histogram start
    hist_start = None
    for i, line in enumerate(lines):
        if line.startswith('# Histogram'):
            hist_start = i + 1
            break
    
    if hist_start is None:
        print("No histogram found")
        return
    
    # Parse histogram rows
    latencies = {}
    for line in lines[hist_start:]:
        if line.startswith('#') or line.strip() == '':
            continue
        parts = line.split()
        if len(parts) < 11:
            continue
        base = int(parts[0])
        for offset, count in enumerate(parts[1:11]):
            latency = base + offset
            latencies[latency] = int(count)
    
    # Find key metrics
    total = sum(latencies.values())
    if total == 0:
        return
    
    # Find mode (most common latency)
    mode = max(latencies, key=latencies.get)
    
    # Find 99th percentile
    cumulative = 0
    p99 = None
    for lat in sorted(latencies.keys()):
        cumulative += latencies[lat]
        if cumulative >= total * 0.99:
            p99 = lat
            break
    
    print(f"Total samples: {total}")
    print(f"Mode: {mode} µs ({latencies[mode]} samples)")
    print(f"99th percentile: {p99} µs")
    print(f"Max: {max(latencies.keys())} µs")

if __name__ == "__main__":
    parse_histogram(sys.argv[1])
```

## Common Pitfalls & Gotchas

1. **Bucket overflow**: If you set `-h 200` but your system occasionally hits 300 µs, those samples go into the overflow counter (`# Histogram Overflows`). Always check this value — if it's non-zero, your histogram is truncated and you need to increase `-h`. A common rookie mistake is seeing a clean histogram but missing the overflow line.

2. **Histogram resolution vs. timer resolution**: The default histogram bucket is 1 µs, but your system timer might have coarser granularity (e.g., 4 µs on some ARM platforms). In that case, you'll see empty buckets between populated ones. This doesn't mean latencies are skipping — it means the hardware can't measure finer. Don't over-interpret gaps in the histogram.

3. **Confusing cumulative vs. per-bucket counts**: The histogram shows per-bucket counts, not cumulative. If you see a column with 50000 samples at 4 µs, that's 50000 wakeups that took *exactly* 4 µs — not 4 µs or less. To find the 99th percentile, you must sum buckets from low to high.

## Try It Yourself

1. **Run a baseline histogram**: Boot your PREEMPT_RT system, run `cyclictest -h 500 -i 1000 -p 99 -a 1 -q -D 120s` and save the output. Calculate the mode, 99th percentile, and max. Then run the same test with a heavy workload (`stress --cpu 4 --io 4`) and compare the histograms. Where did the tail shift?

2. **Detect periodic interference**: Run cyclictest with `-h 200 -i 1000 -p 99 -a 1 -q -D 300s` while also running `trace-cmd record -e syscalls:* -T`. After the test, look at the histogram for bimodal patterns (two distinct peaks). Use `trace-cmd report` to find what syscalls correlate with the higher-latency peak.

3. **Write a histogram comparator**: Modify the Python script above to accept two histogram files and print the difference in mode, p99, and max. Use it to compare a "clean" boot vs. a boot with `nohz_full=1` enabled. Which configuration gives a tighter distribution?

## Next Up

Tomorrow we'll tackle CPU isolation: the `isolcpus`, `nohz_full`, and `rcu_nocbs` kernel boot parameters. These are the knobs that keep the kernel off your real-time CPUs — essential for sub-10 µs latency targets. We'll cover how to configure them, verify they're working, and the common gotchas that can silently break your isolation.
