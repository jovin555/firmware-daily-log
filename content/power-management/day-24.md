---
title: "Day 24: cpufreq: Governors, Policies & DVFS on Embedded"
date: 2026-07-06
tags: ["til", "power-management", "cpufreq", "dvfs", "governors"]
---

## What I Explored Today

I spent the day deep in the Linux cpufreq subsystem, tracing how DVFS (Dynamic Voltage and Frequency Scaling) decisions propagate from userspace governors down to the hardware clock dividers on an i.MX8M Plus. The goal was to understand not just how to switch governors, but how policy boundaries, transition latencies, and hardware constraints interact in real embedded workloads. I instrumented a Yocto-based build with tracepoints and watched frequency scaling in action under a bursty video encode task.

## The Core Concept

DVFS is the primary lever for reducing CPU power during light load, but it's not free. Every frequency transition costs time (microseconds to milliseconds) and energy (charging/discharging rail capacitances). The governor is the policy engine that decides *when* to scale. The policy object defines *which* frequencies are available and *how* the governor interacts with the hardware.

On embedded Linux, the `cpufreq` framework sits between the scheduler and the clock driver. The governor monitors CPU utilization (or a userspace hint) and selects a target frequency. The driver then programs the PLL or divider. The key insight: **governors don't directly set voltage**. That's handled by the `regulator` framework via the OPP (Operating Performance Point) table, which pairs each frequency with a voltage. The governor only requests a frequency; the cpufreq core looks up the OPP and calls the regulator.

The `schedutil` governor is now the default on most modern kernels (since 4.7). It hooks directly into the scheduler's PELT (Per-Entity Load Tracking) signals, giving sub-millisecond response times. On embedded, this matters because a 10 ms delay in ramping up frequency can cause visible frame drops in a video pipeline. The `ondemand` governor, by contrast, samples utilization every 10-80 ms (configurable via `sampling_rate`), which is too slow for interactive workloads.

## Key Commands / Configuration / Code

**1. Inspecting current governor and available frequencies:**
```bash
# Show current governor for CPU0
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
# -> schedutil

# List available governors (compiled into kernel)
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
# -> conservative ondemand userspace powersave performance schedutil

# Show frequency table (in kHz)
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies
# -> 400000 600000 800000 1000000 1200000 1400000 1600000 1800000
```

**2. Switching governor at runtime (no reboot):**
```bash
# Switch to performance (max freq always)
echo performance > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Switch to powersave (min freq always)
echo powersave > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Verify
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

**3. Setting policy boundaries (min/max frequency):**
```bash
# Clamp to 800 MHz - 1.2 GHz
echo 800000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq
echo 1200000 > /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq

# Check current frequency (may differ from target due to latency)
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
```

**4. Tracing DVFS transitions with ftrace:**
```bash
# Enable cpufreq tracepoints
echo 1 > /sys/kernel/tracing/events/power/cpu_frequency/enable
echo 1 > /sys/kernel/tracing/tracing_on

# Run workload, then read trace
cat /sys/kernel/tracing/trace | grep cpu_frequency
# Example output:
#   kworker/0:1-45    [000] ...1   123.456789: cpu_frequency: state=1200000 cpu_id=0
#   kworker/0:1-45    [000] ...1   123.789012: cpu_frequency: state=800000 cpu_id=0
```

**5. Setting governor via device tree (i.MX8M Plus example):**
```dts
&cpu0 {
    operating-points-v2 = <&cpu0_opp_table>;
    clocks = <&clk IMX8MP_CLK_ARM>;
    clock-latency = <150000>;  /* 150 us transition latency */
};
```

## Common Pitfalls & Gotchas

**1. `scaling_cur_freq` is not the instantaneous frequency.** On many SoCs, this file reports the frequency from the *last* governor request, not the current hardware state. The actual hardware frequency may be transitioning. Use `cpufreq-info -f` or read the hardware counter directly (e.g., via the ARM generic timer) for real-time measurement.

**2. `schedutil` can cause thermal throttling on small cores.** Because it responds so fast, it can ramp up frequency before the thermal zone has time to react. On Cortex-A53 clusters, I've seen `schedutil` cause 10-15% more thermal events than `ondemand` under bursty loads. Always pair `schedutil` with a proactive thermal governor (like `step_wise` or `power_allocator`).

**3. Userspace governor + manual frequency setting breaks on hotplug.** If you set a fixed frequency via `userspace` governor and then offline/online a CPU, the governor resets to `performance` on the re-onlined CPU. This is a known kernel behavior (not a bug). Always re-apply the governor after CPU hotplug events in your init script.

**4. Clock latency matters more than you think.** The `clock-latency` value in the OPP table (or device tree) is used by `schedutil` to decide whether to skip a transition. If you set it too low (e.g., 10 us on a PLL that takes 100 us), the governor will issue requests faster than the hardware can respond, causing missed deadlines and frequency overshoot. Measure actual transition time with a scope on the clock output pin.

## Try It Yourself

1. **Profile governor response time:** On your embedded board, run `stress -c 1` in the background while tracing `cpu_frequency` events with ftrace. Switch between `schedutil` and `ondemand`. Measure the time from workload start to first frequency ramp-up. How many milliseconds difference do you see?

2. **Find the optimal min_freq for your workload:** Set `scaling_min_freq` to the second-lowest frequency in your table. Run a real workload (e.g., `ffmpeg` encoding a 1080p clip). Compare total energy consumption (via `perf stat -e power/energy-cores/`) against running at the lowest frequency. You may find that a slightly higher floor reduces runtime enough to save net energy.

3. **Break the governor intentionally:** Set the governor to `userspace`, write a very low frequency (e.g., 200 MHz if available), then launch a GUI application. Observe the system responsiveness. Then write back a higher frequency. This teaches you the cost of DVFS latency better than any datasheet.

## Next Up

Tomorrow: **cpuidle: C-States, Latency Tolerance & Residency** — how the CPU idle subsystem decides when to shut down clock trees and power gates, and why getting residency wrong can cost you more power than staying awake.
