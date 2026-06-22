---
title: "Day 10: CPU Frequency Scaling: cpufreq & performance Mode"
date: 2026-06-22
tags: ["til", "preempt-rt", "cpufreq", "governors", "performance"]
---

## What I Explored Today

Today I dug into how CPU frequency scaling (cpufreq) interacts with real-time workloads. The default `ondemand` or `powersave` governors are designed for power efficiency, but they introduce latency spikes that can destroy deterministic behavior in a PREEMPT_RT system. I tested the `performance` governor, measured the difference in scheduling jitter, and confirmed that frequency transitions are a hidden source of non-determinism that every RT engineer must control.

## The Core Concept

CPU frequency scaling sounds like a power-management problem, not a real-time problem. But here’s the reality: when the cpufreq governor decides to scale down the CPU frequency, the transition itself takes time—typically 100–500 microseconds on x86, and potentially longer on embedded ARM SoCs. During that transition, the CPU may be in an undefined power state, caches can be flushed, and interrupts may be delayed.

For a real-time task with a 1 ms deadline, a 200 µs frequency transition is catastrophic. Worse, the `ondemand` governor samples CPU load every few milliseconds and triggers transitions based on recent utilization. This means your RT task could be preempted by the governor’s workqueue, or the frequency could drop right before your task runs, causing it to miss its deadline.

The `performance` governor locks the CPU at the maximum supported frequency. No transitions, no sampling, no surprises. This is the baseline for any deterministic RT system. Yes, it uses more power. Yes, it generates more heat. But for hard real-time, you trade power for predictability.

On modern x86 systems, there’s an additional layer: Intel’s Hardware P-States (HWP). When HWP is active, the OS can request a frequency range, but the hardware makes the final decision. This is even worse for RT because the transition is opaque to the kernel. The `intel_pstate` driver in passive mode or the `acpi-cpufreq` driver gives you back control.

## Key Commands / Configuration / Code

### 1. Check current governor and available governors

```bash
# Show current governor for all CPUs
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# List available governors
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
# Typical output: performance powersave ondemand conservative schedutil
```

### 2. Set performance governor system-wide

```bash
# Set performance governor for all CPUs
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance > "$cpu"
done

# Verify
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | uniq -c
# Should show: 8 performance  (or however many cores you have)
```

### 3. Check current frequency and hardware limits

```bash
# Current frequency per core
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq

# Hardware min/max (in kHz)
cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq
cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq

# With performance governor, scaling_cur_freq should equal cpuinfo_max_freq
```

### 4. Disable intel_pstate HWP (for Intel systems)

```bash
# Add to kernel command line in /etc/default/grub or bootloader config
# GRUB_CMDLINE_LINUX="intel_pstate=passive"

# Or disable entirely:
# GRUB_CMDLINE_LINUX="intel_pstate=disable"

# After reboot, check driver:
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver
# Should show: acpi-cpufreq (not intel_pstate)
```

### 5. Measure frequency transition latency (simple test)

```bash
# Install rt-tests if not present
# apt-get install rt-tests   (Debian/Ubuntu)

# Run cyclictest with default governor, then with performance
# Compare max latency
cyclictest -l 100000 -m -n -p 99 -i 1000 -h 100
```

## Common Pitfalls & Gotchas

**1. The governor resets after suspend/resume or thermal throttling**
Even with `performance` set, if the system enters suspend or hits a thermal limit, the kernel may revert to a lower frequency or a different governor. Always re-apply the governor after resume, and monitor `dmesg` for thermal throttling events. On production systems, set the governor in a systemd service or init script that runs after resume.

**2. HWP (Hardware P-States) ignores the governor on modern Intel CPUs**
If `intel_pstate` is in active mode (the default on most Skylake and newer), setting `scaling_governor` to `performance` only tells the driver to request max frequency—but the hardware can still autonomously lower it. You must either boot with `intel_pstate=passive` or `intel_pstate=disable` to get deterministic behavior. Check `scaling_driver` to confirm.

**3. Frequency invariance confuses load tracking**
The kernel’s scheduler uses frequency-invariant utilization tracking. When frequency changes, the scheduler adjusts its load estimates. With `performance`, this is stable. But if you switch governors dynamically, the scheduler’s internal state can become inconsistent, leading to suboptimal task placement. Set it once and leave it.

**4. Not all embedded SoCs expose cpufreq**
On some ARM boards (e.g., older Raspberry Pi models), cpufreq may not be available, or the only governor is `performance`. Always check `/sys/devices/system/cpu/cpu0/cpufreq/` exists before scripting. If it doesn’t, the kernel may have been built without `CONFIG_CPU_FREQ`.

## Try It Yourself

1. **Measure the impact of governor switching on latency**: Run `cyclictest` with the `ondemand` governor for 100,000 iterations. Record the max latency. Switch to `performance` and run again. Compare the histograms. On a typical x86 laptop, expect the max latency to drop by 30–50%.

2. **Check if HWP is active on your system**: Run `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver`. If it says `intel_pstate`, check `cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_available_preferences`. If you see `default`, HWP is active. Reboot with `intel_pstate=passive` and re-run your latency test.

3. **Write a systemd service to lock the governor on boot**: Create `/etc/systemd/system/cpufreq-performance.service` that sets `performance` on all CPUs. Enable it with `systemctl enable cpufreq-performance.service`. Test that it survives a reboot and a suspend/resume cycle.

## Next up

Tomorrow I’ll tackle memory management for real-time: **Huge Pages, mlockall & Page Faults in RT**. We’ll look at why TLB misses and page faults are deadly for deadlines, and how to lock your application’s memory to avoid them.
