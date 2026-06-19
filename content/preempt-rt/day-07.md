---
title: "Day 07: Latency Histograms: Interpreting cyclictest Output"
date: 2026-06-19
tags: ["til", "preempt-rt", "histogram", "latency", "analysis"]
---

## What I Explored Today

Today I dug into the histogram output of `cyclictest` — the single most useful tool for validating a PREEMPT_RT system. Raw max-latency numbers are useful for a quick pass/fail, but the histogram tells you the *distribution* of latencies. That distribution reveals whether your system has occasional outliers (which might be acceptable) or a systemic timing problem (which is not). I spent the morning running controlled tests with `-h` and `--histfile`, then parsing the output to understand what the kernel scheduler is actually doing under load.

## The Core Concept

A single max-latency number is a lie. If you run `cyclictest` for 10 minutes and see a max of 150 µs, you have no idea whether that happened once or 10,000 times. The histogram answers that question by bucketing every single wakeup latency into bins (typically 1 µs or 2 µs wide). The shape of the histogram tells you:

- **The mode**: where most latencies cluster (your "normal" latency)
- **The tail**: how far out the worst-case latencies extend
- **The frequency**: how often you hit the tail

A healthy real-time system should have a tight cluster near the minimum latency (often single-digit microseconds on modern hardware) with a long, sparse tail. A system with problems will show a bimodal distribution (two humps) or a "fat tail" where many samples land far from the mode. That fat tail often points to a driver disabling interrupts for too long, a misconfigured timer, or excessive cache thrashing from a noisy neighbor task.

The `cyclictest` histogram is also your best tool for comparing kernel configurations. Run the same test with `CONFIG_PREEMPT_RT` and without — the histogram will show you the improvement in the tail, not just the average.

## Key Commands / Configuration / Code

### Basic histogram run (100,000 samples, 1 µs bins)

```bash
# Run cyclictest with 1 µs histogram bins, 100k samples, on CPU 0
# -h 1000 means bins from 0 to 1000 µs
# -i 200 = interval 200 µs, -t 1 = one thread
cyclictest -t 1 -p 99 -i 200 -d 0 -a 0 -h 1000 -n -m -l 100000
```

The `-n` flag uses `clock_nanosleep()` instead of `nanosleep()` — critical for PREEMPT_RT because it avoids the glibc wrapper's internal locking. The `-m` flag locks memory to prevent page faults during the test.

### Saving histogram to file for analysis

```bash
# Write histogram to file, then plot with gnuplot
cyclictest -t 1 -p 99 -i 200 -d 0 -a 0 -h 1000 -n -m -l 100000 \
  --histfile=rt_latency_hist.txt

# The file format: first column is bin start (µs), subsequent columns are counts per thread
# Column header: # Min Latencies: 3
# Then: 0 0 0 0  ... (bin 0: count for thread 0, thread 1, ...)
```

### Parsing the histogram with awk

```bash
# Extract the tail (bins > 100 µs) from a saved histogram
# This shows you how many samples exceed 100 µs
awk 'NR > 2 && $1 > 100 { sum += $2 } END { print "Samples >100µs:", sum }' \
  rt_latency_hist.txt
```

### Generating a quick plot with gnuplot

```bash
# Plot histogram (single-threaded case, column 2 is the count)
gnuplot -e "
  set terminal dumb size 80, 30;
  set xlabel 'Latency (µs)';
  set ylabel 'Count';
  set logscale y;
  plot 'rt_latency_hist.txt' using 1:2 with lines title 'Latency Distribution';
"
```

This gives you an ASCII plot right in the terminal — no X11 needed. For real analysis, pipe to a PNG with `set terminal png`.

## Common Pitfalls & Gotchas

### 1. Histogram bin width mismatch
If you use `-h 1000` but your system has latencies up to 2000 µs, everything above 1000 µs gets silently dropped into the overflow bin. You won't see them in the histogram output. Always check the "Max Latencies" line printed to stderr — if it's suspiciously close to your `-h` value, increase the bin count.

### 2. Forgetting `-n` (clock_nanosleep)
Without `-n`, `cyclictest` uses the glibc `nanosleep()` wrapper, which on some architectures acquires a mutex internally. This adds artificial jitter that looks like a kernel problem. Always use `-n` on PREEMPT_RT systems. The difference can be 10-20 µs of phantom latency.

### 3. Interpreting multi-threaded histograms
When you run with `-t 4` (four threads), the histogram file has four count columns. The first column is the bin, then columns 2-5 are counts per thread. If you sum them without thinking, you'll double-count. Use `awk '{ sum=0; for(i=2;i<=NF;i++) sum+=$i; print $1, sum }'` to get the aggregate distribution.

## Try It Yourself

1. **Baseline histogram**: Run `cyclictest -t 1 -p 99 -i 200 -a 0 -h 500 -n -m -l 50000 --histfile=baseline.txt` on an idle system. Plot the histogram and note the 99.9th percentile latency (the bin where 99.9% of samples fall below).

2. **Stress test comparison**: Repeat the same test while running `stress --cpu 4 --io 2 --vm 2 --vm-bytes 128M` in another terminal. Compare the histograms — how much does the tail grow? Is the mode affected?

3. **IRQ affinity test**: Run the cyclictest thread on CPU 0, then move all interrupt handlers off CPU 0 using `/proc/irq/*/smp_affinity`. Re-run the histogram. The tail should shrink noticeably. Use `cat /proc/interrupts` to verify the IRQ distribution changed.

## Next Up

Tomorrow we'll tackle CPU isolation: the `isolcpus`, `nohz_full`, and `rcu_nocbs` kernel boot parameters. These are the knobs that keep the kernel's housekeeping tasks off your real-time CPUs — without them, your carefully tuned cyclictest histogram will never look as good as it could.
