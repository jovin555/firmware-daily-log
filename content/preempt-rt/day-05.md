---
title: "Day 05: cyclictest: Measuring Worst-Case Latency"
date: 2026-06-17
tags: ["til", "preempt-rt", "cyclictest", "latency", "measurement"]
---

## What I Explored Today

Today I put the PREEMPT_RT kernel through its paces with `cyclictest`, the de facto standard for measuring scheduling latency in real-time Linux systems. I ran a series of measurements on a Raspberry Pi 4 (quad-core Cortex-A72) running a 5.15.84-rt54 kernel, collecting both average and worst-case latency numbers under various conditions. The goal was to understand not just how to run the tool, but how to interpret its output and identify where latency creeps in.

## The Core Concept

`cyclictest` measures the difference between *when a thread expects to wake up* and *when it actually wakes up*. This delta—the scheduling latency—is the fundamental metric of real-time performance. The tool creates a set of real-time threads (SCHED_FIFO by default), each sleeping for a fixed interval (default 1000 µs) and then recording the time it takes to resume execution.

Why worst-case latency matters: In a hard real-time system, missing a single deadline can mean data corruption, equipment damage, or safety failure. Average latency is nearly irrelevant—you care about the maximum observed delay. `cyclictest` runs for hours or days to capture these rare, high-latency events that might only occur under specific interrupt or scheduling conditions.

The tool reports three key values per thread: minimum, average, and maximum latency. The maximum is the one that keeps real-time engineers awake at night. A typical target for a soft real-time system might be <100 µs worst-case; hard real-time often requires <10 µs deterministic behavior.

## Key Commands / Configuration / Code

### Basic Latency Measurement

The most common invocation for a quick check:

```bash
# Run 4 threads (one per core), 1000 µs interval, SCHED_FIFO priority 80
# Output histogram with 1 µs buckets, run for 60 seconds
cyclictest -t 4 -p 80 -i 1000 -h 100 -D 60s
```

- `-t 4`: Number of test threads (typically match CPU count)
- `-p 80`: Real-time priority (1-99, higher = more urgent)
- `-i 1000`: Interval in microseconds between wakeups
- `-h 100`: Histogram buckets from 0 to 100 µs
- `-D 60s`: Duration of the test

### Isolating a Core for Cleaner Results

To avoid interference from other processes, pin the test to a dedicated core:

```bash
# Isolate CPU 3, run one thread there
cyclictest -a 3 -t 1 -p 80 -i 1000 -h 200 -D 300s
```

The `-a` flag pins threads to specific CPUs. For multi-threaded tests, `-a 0-3` spreads threads across cores 0-3.

### Background Load Test (Realistic Scenario)

Run cyclictest while stressing the system to see worst-case under load:

```bash
# Terminal 1: Start cyclictest with background load
cyclictest -t 4 -p 80 -i 1000 -h 500 -D 600s --mlockall --smp

# Terminal 2: Generate memory pressure
stress-ng --vm 4 --vm-bytes 512M --vm-keep -t 600s

# Terminal 3: Generate CPU load
stress-ng --cpu 4 --cpu-method matrixprod -t 600s
```

The `--mlockall` flag locks all memory to prevent page faults from introducing latency. The `--smp` flag enables symmetric multiprocessing mode for better accuracy on multi-core systems.

### Parsing the Output

Typical output looks like this:

```
# /dev/cpu_dma_latency set to 0 us
policy: fifo: loadavg: 0.00 0.01 0.02 1/143 1234

T: 0 (12345) P: 80 I:1000 C:   60000 Min:      2 Act:    4 Avg:    5 Max:      47
T: 1 (12346) P: 80 I:1000 C:   60000 Min:      2 Act:    3 Avg:    4 Max:      38
T: 2 (12347) P: 80 I:1000 C:   60000 Min:      2 Act:    5 Avg:    5 Max:      52
T: 3 (12348) P: 80 I:1000 C:   60000 Min:      2 Act:    3 Avg:    4 Max:      41
```

- `Min`: Best-case latency (usually 1-3 µs on modern hardware)
- `Act`: Most recent measurement
- `Avg`: Mean latency across all samples
- `Max`: **Worst-case latency**—the number you care about

### Histogram Mode for Deep Analysis

```bash
# Generate a detailed histogram and save to file
cyclictest -t 4 -p 80 -i 1000 -h 1000 -D 3600s -m > latency_histogram.txt
```

The histogram shows how many samples fell into each 1 µs bucket, making it easy to spot outliers. A healthy system shows a tight cluster near the minimum with a long, thin tail.

## Common Pitfalls & Gotchas

### 1. Running Without Root Privileges

`cyclictest` requires `CAP_SYS_NICE` or root to set real-time priorities. Without it, threads run at SCHED_OTHER and the results are meaningless—you'll see latencies in the milliseconds. Always run with `sudo` or set the capability:

```bash
sudo setcap cap_sys_nice=ep /usr/bin/cyclictest
```

### 2. Ignoring CPU Isolation and IRQ Affinity

If you don't isolate a core and pin IRQs away from it, interrupt handlers can preempt your test thread. On a Raspberry Pi, the USB and network interrupts can cause 50-100 µs spikes. Use `isolcpus=3` on the kernel command line and set IRQ affinity via `/proc/irq/*/smp_affinity` to keep interrupts off your measurement core.

### 3. Misinterpreting Single-Run Results

A 10-second test that shows 20 µs max latency doesn't prove your system is deterministic. Rare events (cache misses, TLB flushes, interrupt storms) might only occur once per hour. Run for at least 30 minutes, ideally overnight, to capture true worst-case behavior. The histogram's tail is your friend—if it's still growing at the end of the test, you haven't run long enough.

## Try It Yourself

1. **Baseline measurement**: Run `cyclictest -t 4 -p 80 -i 1000 -h 200 -D 300s` on your PREEMPT_RT system. Record the Max value for each thread. Then run the same test without `--mlockall`—how much does the worst-case increase?

2. **Interrupt interference test**: Check which IRQs are hitting CPU 0 with `cat /proc/interrupts`. Then run `cyclictest -a 0 -t 1 -p 80 -i 1000 -h 500 -D 120s`. Move the network IRQ to another core using `/proc/irq/<number>/smp_affinity` and re-run. Compare the max latencies.

3. **Histogram analysis**: Run `cyclictest -t 1 -p 80 -i 1000 -h 1000 -D 600s -m` and save the output. Plot the histogram (bucket index vs. count) using any tool. Identify the 99.9th percentile latency—this is often more useful than the absolute max for soft real-time systems.

## Next Up

Tomorrow we'll stress-test our real-time system with `hackbench` and `stress-ng` to generate realistic load patterns—CPU, memory, disk I/O, and network pressure—while measuring how latency degrades under fire. You'll learn which workloads break your deterministic guarantees and how to harden your system against them.
