---
title: "Day 25: cpuidle: C-States, Latency Tolerance & Residency"
date: 2026-07-07
tags: ["til", "power-management", "cpuidle", "c-states", "residency"]
---

## What I Explored Today

Today I dove into the Linux `cpuidle` subsystem — the kernel component responsible for deciding when to put idle CPUs into deeper sleep states (C-States) and for how long. I’ve always known that C-States save power by clock-gating or power-gating processor cores, but I never fully understood the tension between *latency tolerance* and *minimum residency*. After tracing through `/sys/devices/system/cpu/cpu0/cpuidle/` and reading the governor source (`menu` and `ladder`), I now see why a poorly tuned idle policy can wreck real-time performance or waste battery life. This is the layer where microseconds matter.

## The Core Concept

Every modern CPU has multiple idle states, from C0 (active) through C1 (halt), C1E (enhanced halt), C6 (power-gated), and sometimes deeper package states like C7 or C10. The deeper the state, the more power you save — but the longer it takes to wake up. That wake-up latency is the *exit latency*, and it’s the enemy of low-latency workloads.

The kernel’s `cpuidle` governor (usually `menu` on tickless systems) must answer one question: *Given the expected idle duration, which C-State can I enter without oversleeping the next interrupt?* The answer depends on two per-state parameters:

- **target_residency**: the minimum time the CPU must stay idle to break even on the energy cost of entering/exiting the state.
- **exit_latency**: the worst-case time to return to C0.

If the predicted idle time is shorter than `target_residency`, the governor picks a shallower state. If it’s longer, it goes deeper. The `menu` governor also considers the *latency tolerance* of the running task (via PM QoS) — if a task says “I can tolerate 100 µs of wake-up delay,” the governor will not enter a state with exit latency > 100 µs.

This is not just theory. I’ve seen embedded systems where a network driver’s interrupt coalescing timer was set too aggressively, causing the CPU to enter C6 and miss the next network frame because the exit latency (200 µs) exceeded the inter-frame gap. The fix was either to tune the governor or to use `PM QoS` to cap the allowed C-State depth.

## Key Commands / Configuration / Code

### 1. Inspect available C-States and their parameters

```bash
# List all idle states for CPU 0
ls /sys/devices/system/cpu/cpu0/cpuidle/state0/

# View parameters for state0 (usually C1)
cat /sys/devices/system/cpu/cpu0/cpuidle/state0/name
cat /sys/devices/system/cpu/cpu0/cpuidle/state0/latency   # exit latency in µs
cat /sys/devices/system/cpu/cpu0/cpuidle/state0/residency # target residency in µs
cat /sys/devices/system/cpu/cpu0/cpuidle/state0/usage     # times entered
cat /sys/devices/system/cpu/cpu0/cpuidle/state0/time      # total time in state (µs)
```

### 2. Check which cpuidle governor is active

```bash
cat /sys/devices/system/cpu/cpuidle/current_governor
# Typically "menu" on modern kernels, "ladder" on older or UP systems
```

### 3. Set a global latency tolerance via PM QoS

```bash
# Write a latency tolerance in µs to the PM QoS device
# This prevents cpuidle from entering states with exit latency > 100 µs
echo 100 > /dev/cpu_dma_latency
```

This is the canonical way for a real-time process to say “I need low wake-up latency.” The file descriptor must be held open; closing it reverts the constraint.

### 4. Trace idle state transitions with ftrace

```bash
# Enable cpuidle tracepoints
echo 1 > /sys/kernel/debug/tracing/events/power/cpu_idle/enable
echo 1 > /sys/kernel/debug/tracing/tracing_on
cat /sys/kernel/debug/tracing/trace_pipe
# Sample output:
#   <idle>-0     [000] d..2.  1234.567890: cpu_idle: state=3 cpu=0
```

### 5. Kernel code snippet: governor decision logic (simplified)

```c
// From drivers/cpuidle/governors/menu.c (conceptual)
static int menu_select(struct cpuidle_driver *drv, struct cpuidle_device *dev)
{
    int i;
    unsigned int predicted_us = get_typical_interval(dev);
    unsigned int latency_req = pm_qos_request(PM_QOS_CPU_DMA_LATENCY);

    for (i = 0; i < drv->state_count; i++) {
        struct cpuidle_state *s = &drv->states[i];
        if (s->exit_latency > latency_req)
            continue;               // Skip states that violate latency tolerance
        if (s->target_residency > predicted_us)
            continue;               // Skip states we can't stay in long enough
        break;                      // Pick the deepest valid state
    }
    return i;
}
```

## Common Pitfalls & Gotchas

1. **PM QoS file descriptor must stay open.** Writing to `/dev/cpu_dma_latency` and then closing the file descriptor immediately removes the constraint. Many developers write the value and exit, wondering why nothing changed. You must hold the FD open (e.g., in a background daemon or by using `exec 3>/dev/cpu_dma_latency` in a shell script).

2. **`target_residency` is not the same as `exit_latency`.** I’ve seen people confuse these two. `exit_latency` is the wake-up delay; `target_residency` is the break-even time. A state might have 50 µs exit latency but require 2000 µs residency to be worthwhile. Entering it for 100 µs wastes more energy than staying in C1.

3. **Interrupt coalescing can fight C-States.** If a device (e.g., Ethernet or USB) fires interrupts too frequently, the CPU never stays idle long enough to enter deep C-States. Conversely, if coalescing is too long, the CPU enters C6 and then misses the next interrupt because exit latency eats into the coalescing window. Always profile the actual idle duration distribution with `turbostat` or `powertop` before tuning.

## Try It Yourself

1. **Profile your system’s C-State residency.** Run `sudo powertop --csv=powertop.csv` for 60 seconds, then grep for `C-state` in the CSV. Which state has the highest residency? Compare with `cat /sys/devices/system/cpu/cpu0/cpuidle/state*/time` to verify.

2. **Force a latency constraint and observe the effect.** Open a terminal and run:  
   `exec 3>/dev/cpu_dma_latency && echo 50 > /dev/cpu_dma_latency`  
   Then in another terminal, run `turbostat --quiet --show C1,C2,C3 --interval 2`.  
   Watch the deeper C-States disappear. Close the first terminal to release the constraint and see them return.

3. **Trace idle transitions during a network ping flood.** Enable the `cpu_idle` tracepoint, then ping your gateway at 1 ms intervals. Observe which C-States are entered. Does the governor ever choose C6? If not, why? (Hint: look at the predicted idle duration vs. target_residency.)

## Next Up

Tomorrow we tackle **devfreq: Dynamic Voltage & Frequency Scaling** — the DVFS counterpart to cpuidle. While cpuidle manages *idle* power, devfreq manages *active* power by scaling voltage and frequency for devices like GPUs, memory controllers, and interconnects. We’ll look at governors (`simple_ondemand`, `powersave`), polling intervals, and how to tune them for your SoC’s power-performance curve.
