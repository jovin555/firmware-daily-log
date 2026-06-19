---
title: "Day 07: cpuidle: C-States, Latency Tolerance & Residency"
date: 2026-06-19
tags: ["til", "power-management", "cpuidle", "c-states", "residency"]
---

## What I Explored Today

Today I dug into the Linux `cpuidle` subsystem — the kernel's mechanism for putting idle CPUs into progressively deeper sleep states (C-States) to save power. I focused on the three factors that determine which state the governor selects: the idle duration prediction, the exit latency penalty, and the minimum residency requirement. I also poked at the `intel_idle` driver on my x86 test box and watched how `turbostat` reveals the real-time state residency distribution.

## The Core Concept

C-States (C0, C1, C1E, C6, C8, C10 on modern x86) define a hierarchy of CPU sleep depths. C0 is active execution. C1 halts the core but keeps caches coherent. Deeper states (C6+) save more power by flushing L1/L2 caches and reducing voltage, but they take longer to wake from — that's the *exit latency*.

The kernel's `cpuidle` governor (usually `menu` or `teo`) must answer one question: *"How long will this CPU stay idle?"* If it guesses wrong and picks a deep C-state, the CPU will burn extra energy waking up (exit latency overhead) and may miss a deadline. If it picks too shallow a state, it wastes power.

The key metric is **target residency** — the minimum idle duration required for a given C-state to break even on energy. If the predicted idle time is shorter than the target residency, the governor must choose a shallower state. This is where **latency tolerance** comes in: some workloads (audio, USB polling) can't tolerate long wake-up delays, so the governor also respects a per-process `pm_qos_resume_latency_us` constraint.

On embedded/Linux systems, you can observe and tune this via sysfs, and you can even write a custom governor if the defaults don't fit your workload.

## Key Commands / Configuration / Code

### 1. Inspect available C-states and their parameters

```bash
# List all C-states for CPU0, with latency and residency in microseconds
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/name
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/latency
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/residency
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/power  # estimated mW

# Example output (Intel Tiger Lake):
# state0: POLL   latency=0  residency=0  power=0
# state1: C1    latency=2  residency=2  power=1000
# state2: C1E   latency=10 residency=20 power=800
# state3: C6    latency=130 residency=400 power=400
# state4: C8    latency=350 residency=900 power=200
# state5: C10   latency=600 residency=2000 power=10
```

### 2. Monitor real-time C-state residency

```bash
# turbostat shows C-state % residency per CPU, updated every 5 seconds
sudo turbostat --quiet --show CPU,POLL,C1,C1E,C6,C8,C10 --interval 5

# Or use cpuidle's own counters
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/usage
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/time   # total microseconds spent
```

### 3. Set a per-process latency tolerance (PM QoS)

```bash
# Force a process to prevent deep C-states (max 50 µs exit latency)
# Useful for audio or interrupt-driven I/O
echo 50 > /proc/$(pgrep my_audio_app)/pm_qos_resume_latency_us

# Or set a system-wide floor (prevents C6+ on all CPUs)
echo 100 > /dev/cpu_dma_latency  # write file descriptor, keep open
```

### 4. Change the cpuidle governor at runtime

```bash
# Check current governor
cat /sys/devices/system/cpu/cpuidle/current_governor

# Switch to 'teo' (Timer Events Oriented) — better for tickless kernels
echo teo > /sys/devices/system/cpu/cpuidle/current_governor

# Available governors: menu, teo, ladder (deprecated)
```

### 5. Disable a specific C-state (e.g., C6 on CPU0)

```bash
# Write 1 to disable, 0 to enable
echo 1 > /sys/devices/system/cpu/cpu0/cpuidle/state3/disable
```

## Common Pitfalls & Gotchas

**1. `intel_idle` vs `acpi_idle` — they report different data.**  
On modern Intel hardware, `intel_idle` bypasses ACPI and uses hardcoded tables from the CPU microcode. The latency/residency values in sysfs may be optimistic. Always cross-check with `turbostat -v` to see the actual hardware C-state limits. If you see `C1` residency at 99% but power draw is still high, the driver might be lying about C6 availability.

**2. `pm_qos_resume_latency_us` is per-process, but the kernel aggregates the minimum.**  
If one process sets a 50 µs limit and another sets 200 µs, the governor uses 50 µs. This means a single misconfigured process can prevent deep C-states system-wide. Use `turbostat` to spot unexpectedly low C6+ residency, then check `/proc/*/pm_qos_resume_latency_us` for offenders.

**3. Target residency is not a hard guarantee — it's a break-even estimate.**  
The governor uses a *predicted* idle time, which is often wrong. On tickless kernels, the `teo` governor uses timer event distance as a hint. If your workload has bursty idle patterns (e.g., 100 µs idle, 10 µs busy, repeat), the governor will oscillate between C1 and C6, causing extra wake-up overhead. You may need to pin the CPU to C1 only via `cpuidle.state3.disable=1` on the kernel cmdline.

## Try It Yourself

1. **Profile your system's C-state distribution**  
   Run `sudo turbostat --quiet --show CPU,POLL,C1,C1E,C6,C8,C10 --interval 1` for 30 seconds while your system is idle. Note which C-states are never entered. Then run a `stress --cpu 4` and observe how C0 dominates.

2. **Force a shallow C-state ceiling**  
   Write `echo 1 > /sys/devices/system/cpu/cpu0/cpuidle/state3/disable` to block C6 on CPU0. Run `turbostat` again and compare power draw (use `--show PkgWatt`). You should see a measurable increase in package power.

3. **Simulate a latency-sensitive workload**  
   Write a small C program that sleeps for 500 µs in a loop (using `clock_nanosleep`). Before running it, set its PM QoS to 50 µs: `echo 50 > /proc/$(pgrep your_prog)/pm_qos_resume_latency_us`. Run `turbostat` and verify that C6+ residency drops to near zero on the pinned CPU.

## Next Up

Tomorrow I'll dive into **devfreq: Dynamic Voltage & Frequency Scaling** — the kernel's framework for scaling CPU and memory bus frequencies based on utilization. We'll look at governors like `userspace`, `ondemand`, and `passive`, and how to tune them for battery life vs. performance on embedded devices.
