---
title: "Day 06: cpufreq: Governors, Policies & DVFS on Embedded"
date: 2026-06-18
tags: ["til", "power-management", "cpufreq", "dvfs", "governors"]
---

## What I Explored Today

Today I dug into the Linux cpufreq subsystem — the kernel's mechanism for dynamic voltage and frequency scaling (DVFS) on CPUs. I traced how governors decide when to ramp up or down, how policies bind those decisions to hardware, and what this looks like on an embedded ARM Cortex-A72 platform running Yocto. The goal: understand not just how to *set* a governor, but how to *choose* one based on workload latency and power constraints.

## The Core Concept

DVFS is the most direct lever we have for trading CPU performance for power. The cpufreq subsystem abstracts this into three layers:

1. **Governors** — algorithms that decide the target frequency based on CPU load, user hints, or thermal feedback.
2. **Policies** — per-CPU or per-cluster objects that bind a governor to a set of frequency/voltage operating points (OPPs).
3. **Drivers** — hardware-specific code that programs the actual clock dividers and voltage regulators.

The key insight: on embedded systems, you rarely want the same governor for all cores. A real-time audio thread on core 0 needs `performance`; a background logging thread on core 1 can use `powersave`. Modern kernels support per-policy governors, but you must verify your hardware supports independent per-core DVFS (many ARM big.LITTLE clusters share a voltage domain).

The *why*: idle power dominates on embedded, but active power scales as `P ∝ C × V² × f`. Dropping frequency by 20% at the same voltage saves 20% dynamic power. Dropping voltage *and* frequency (true DVFS) saves quadratically. The governor's job is to find the lowest stable voltage-frequency pair that meets the current performance requirement.

## Key Commands / Configuration / Code

### 1. Inspecting available governors and frequencies
```bash
# List all governors compiled into the kernel
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
# Output: conservative ondemand userspace powersave performance schedutil

# List all frequency steps (OPPs) for CPU0
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies
# Output: 408000 600000 816000 1008000 1200000 1416000 1608000 1800000
```

### 2. Changing governor and frequency (userspace governor)
```bash
# Switch CPU0 to userspace governor
echo userspace > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Manually set frequency to 1.2 GHz (must be in available list)
echo 1200000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_setspeed

# Verify current frequency
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
```

### 3. Setting governor via kernel bootargs (Yocto/Buildroot)
```c
// In your device tree or kernel config, set default governor
// File: arch/arm/boot/dts/myboard.dts
&cpu0 {
    operating-points = <
        408000   850000
        600000   900000
        816000   950000
        1008000  1000000
        1200000  1050000
    >;
};

// Kernel cmdline to force schedutil on all CPUs
// cpufreq.default_governor=schedutil
```

### 4. Per-policy governor assignment (big.LITTLE example)
```bash
# On a 2-cluster system (4xA53 + 4xA72)
# Cluster 0 (little cores)
echo schedutil > /sys/devices/system/cpu/cpufreq/policy0/scaling_governor

# Cluster 1 (big cores)
echo performance > /sys/devices/system/cpu/cpufreq/policy4/scaling_governor
```

### 5. Monitoring DVFS transitions in real-time
```bash
# Watch frequency changes across all CPUs (1s refresh)
watch -n1 'cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq'

# Use tracepoint to log every frequency change
trace-cmd record -e cpufreq_interactive_setspeed sleep 5
trace-cmd report | head -20
```

## Common Pitfalls & Gotchas

### 1. Shared voltage domains break per-core DVFS
On many SoCs (e.g., i.MX8M, Rockchip RK3399), all cores in a cluster share a single voltage rail. Setting different frequencies per core is impossible — the kernel enforces the *maximum* requested frequency across the cluster. Always check `cat /sys/devices/system/cpu/cpu*/cpufreq/related_cpus` to see which CPUs are coupled.

### 2. `ondemand` vs `schedutil` on RT kernels
The `ondemand` governor samples load every ~10ms, which introduces latency spikes on PREEMPT_RT systems. `schedutil` reads utilization directly from the scheduler (per-task, per-CPU) and reacts in microseconds. For audio or control loops, always prefer `schedutil` or `performance`.

### 3. Thermal throttling silently overrides governors
When the SoC hits a thermal trip point, the thermal framework (via `cpufreq_cooling`) will cap the maximum frequency regardless of governor. I've debugged systems where `performance` governor appeared broken — it was actually thermal throttling at 85°C. Monitor with `cat /sys/class/thermal/thermal_zone*/temp` and check `cooling_device` stats.

## Try It Yourself

1. **Governor latency shootout**: Write a small C program that runs a tight loop of 100k integer operations. Time it under `performance`, `ondemand`, and `schedutil` governors. Measure wall-clock time *and* total energy (via `perf stat -e power/energy-pkg/` if available). Which governor gives the best perf/watt for a burst workload?

2. **Userspace DVFS sweep**: Set governor to `userspace`, then iterate through all available frequencies. At each step, run a fixed workload (e.g., `openssl speed -elapsed md5`) and record both completion time and current draw from a USB power monitor. Plot frequency vs. energy-per-operation — you'll see the quadratic voltage effect.

3. **Per-cluster governor isolation**: On a big.LITTLE board (e.g., Odroid N2+), pin a CPU-bound task to the little cluster with `taskset -c 0-3` and set its governor to `powersave`. Simultaneously, run a latency-sensitive task on the big cluster with `performance`. Verify with `htop` that frequencies differ per cluster.

## Next Up

Tomorrow: **cpuidle: C-States, Latency Tolerance & Residency** — we'll dive into the idle subsystem, learn how C-states trade wake latency for power savings, and why `menu` governor's residency math is critical for battery life on embedded Linux.
