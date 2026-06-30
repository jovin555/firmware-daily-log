---
title: "Day 18: Full Review & Project: Certifiable Latency Report"
date: 2026-06-30
tags: ["til", "preempt-rt", "review", "project", "report"]
---

## What I Explored Today

After seventeen days of drilling into PREEMPT_RT patches, cyclictest metrics, interrupt threading, and kernel configuration, today I stepped back to build something that matters in production: a certifiable latency report. In safety-critical and industrial systems—think medical devices, avionics, or CNC controllers—you cannot just say "it's real-time." You must prove worst-case latency with statistical confidence. Today I assembled a repeatable test harness that generates a latency histogram, computes the 99.99th percentile, and produces a human-readable report suitable for a design review or regulatory submission.

## The Core Concept

A "certifiable latency report" is not about running cyclictest once and noting the max. That max is a single sample, vulnerable to noise. Certification bodies (IEC 61508, DO-178C, ISO 26262) demand evidence that the system meets timing constraints under representative load. The core idea is threefold:

1. **Stress the system** — run cyclictest alongside a synthetic workload that mimics production (e.g., network traffic, disk I/O, heavy interrupt load).
2. **Collect enough samples** — a few thousand is not enough. You need millions to capture rare events. The rule of thumb: for a 99.99th percentile estimate with reasonable confidence, collect at least 1/ε samples, where ε = 0.0001 → 10,000 samples *per percentile bin*. I aim for 5–10 million.
3. **Report the distribution, not just the max** — the histogram reveals multimodality, jitter clusters, and whether the max is an outlier or a systematic issue.

Today’s project automates this: a shell script that runs cyclictest with `--histogram` and `--histfile`, then post-processes with `awk` and `gnuplot` to produce a PDF report.

## Key Commands / Configuration / Code

### 1. The stress harness

I use `stress-ng` to load the CPU, memory, and I/O subsystems. This is not random—it mimics a typical embedded workload with periodic timers, context switches, and cache thrashing.

```bash
# Run in background: 4 CPU stressors, 2 I/O stressors, 2 VM stressors
stress-ng --cpu 4 --io 2 --vm 2 --vm-bytes 128M \
          --timer 2 --timeout 300s &
STRESS_PID=$!
```

### 2. Cyclictest with histogram output

The key flags: `--histogram=us` (bucket width in microseconds), `--histfile` (write raw data), `--interval=1000` (1 ms timer), `--distance=0` (no staggering for deterministic pattern).

```bash
# Run for 300 seconds, 1 kHz timer, record histogram
cyclictest --mlockall --smp --priority=80 \
           --interval=1000 --distance=0 \
           --histogram=1 --histfile=latency_hist.dat \
           --duration=300s
```

### 3. Post-processing with awk

Extract the 99.99th percentile and total samples from the histogram file. The histogram format is: `# <latency_us> <count_cpu0> <count_cpu1> ...`. We sum counts and compute cumulative distribution.

```bash
awk '
BEGIN { total=0; threshold=0.9999 }
/^[0-9]/ {
    for(i=2; i<=NF; i++) {
        count[$1] += $i
        total += $i
    }
}
END {
    cum=0
    for(lat in count) {
        cum += count[lat]
        if(cum/total >= threshold) {
            printf "99.99th percentile: %d us\n", lat
            printf "Total samples: %d\n", total
            exit
        }
    }
}' latency_hist.dat
```

### 4. Generate the report PDF

I use `gnuplot` to render a histogram with vertical lines at the 99th, 99.9th, and 99.99th percentiles.

```gnuplot
set terminal pdf enhanced font "Helvetica,10"
set output "latency_report.pdf"
set title "PREEMPT_RT Latency Distribution (300s, 1kHz timer)"
set xlabel "Latency (us)"
set ylabel "Frequency (log scale)"
set logscale y
set style data histogram
set style histogram rowstacked
set boxwidth 0.9 relative
set style fill solid 0.5 border -1
plot "latency_hist.dat" using 1:2 title "CPU0" with boxes, \
     "latency_hist.dat" using 1:3 title "CPU1" with boxes
```

Run with: `gnuplot plot_latency.gp`

### 5. Full automation script (skeleton)

```bash
#!/bin/bash
# cert_latency_report.sh — generates a certifiable latency report

DURATION=300
HISTFILE="latency_hist.dat"
REPORT="latency_report.pdf"

echo "Starting stress workload..."
stress-ng --cpu 4 --io 2 --vm 2 --vm-bytes 128M --timer 2 --timeout ${DURATION}s &
STRESS_PID=$!

echo "Running cyclictest (${DURATION}s)..."
cyclictest --mlockall --smp --priority=80 \
           --interval=1000 --distance=0 \
           --histogram=1 --histfile=${HISTFILE} \
           --duration=${DURATION}s

kill $STRESS_PID 2>/dev/null
wait $STRESS_PID 2>/dev/null

echo "Computing percentiles..."
awk '...' ${HISTFILE} > percentiles.txt

echo "Generating PDF report..."
gnuplot plot_latency.gp

echo "Report saved: ${REPORT}"
```

## Common Pitfalls & Gotchas

1. **Histogram bucket width too coarse** — Using `--histogram=10` (10 µs buckets) hides micro-jitter. Always use `--histogram=1` (1 µs resolution) for certification. The file grows, but the data is defensible.

2. **Not pinning cyclictest to isolated CPUs** — If you run cyclictest on a CPU that also handles network interrupts, you measure noise, not the kernel’s real-time capability. Use `taskset` or `cset shield` to isolate cyclictest to dedicated cores.

   ```bash
   cset shield --cpu 1-3   # isolate CPUs 1-3
   cset shield --exec -- cyclictest --smp --priority=80 ...
   ```

3. **Forgetting to disable power management** — C-states, P-states, and CPU frequency scaling inject latency spikes. Before any certification run, set the governor to `performance` and disable deep C-states:

   ```bash
   cpupower frequency-set -g performance
   cpupower idle-set -D 1   # disable C-states deeper than C1
   ```

## Try It Yourself

1. **Run the full report on your PREEMPT_RT system** — Use the script above (or adapt it) to generate a 5-minute latency report. Compare the 99.99th percentile to the absolute max. Are they close? If not, investigate the outliers.

2. **Modify the workload** — Replace `stress-ng` with a workload that mimics your application: e.g., `iperf3` for network traffic, `dd` for disk I/O, or a custom periodic task using `timerfd`. Re-run the report and note how the tail latency changes.

3. **Cross-validate with trace-cmd** — For the worst latency event (the max), use `trace-cmd record -e 'sched_switch' -e 'irq_handler_entry'` during a cyclictest run. Then `trace-cmd report` to see exactly what preempted the cyclictest thread. This turns a number into a root-cause.

## Next Up

Tomorrow is the final review of the series: **Day 19: Full Review — What We Learned & Where to Go Next**. I’ll summarize the key mental models, the most dangerous pitfalls across all 18 days, and the roadmap for going deeper (e.g., integrating with Yocto, building a custom RT appliance, or preparing for a real certification audit).
