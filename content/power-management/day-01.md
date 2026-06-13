---
title: "Day 01: Embedded Power Management: Goals, Trade-offs & Standards"
date: 2026-06-13
tags: ["til", "power-management", "power", "standards"]
---

## What I Explored Today

Today I kicked off a deep dive into embedded power management by mapping out the foundational landscape: why we care, what we're optimizing for, and the standards that govern real-world implementations. I focused on the fundamental tension between performance, battery life, and thermal constraints, and surveyed the key industry standards—ACPI, PM QoS, and the Linux kernel's PM subsystem—that every embedded engineer must understand before touching a single register or governor.

## The Core Concept

Power management in embedded systems isn't about "saving power" in isolation. It's about **maximizing useful work per unit of energy** while staying within thermal and latency budgets. The core trade-off triangle is:

- **Performance** — how fast can we execute tasks
- **Energy** — how much battery or thermal headroom we consume
- **Latency** — how quickly we can respond to events

Every power management decision—from selecting a sleep state to tuning a CPU governor—is a point in this triangle. You cannot maximize all three simultaneously. A deep sleep state (e.g., `WFI` on ARM, `C6` on x86) saves energy but incurs wake-up latency. A race-to-idle strategy burns energy quickly to finish a task and then sleep longer, which works well for bursty workloads but fails for continuous sensor polling.

The **why** is simple: embedded devices are constrained by physics. A battery has finite capacity. A passive heatsink has a thermal limit. A real-time control loop has a deadline. Power management is the art of navigating these constraints without violating system requirements.

The standards that codify this:

- **ACPI (Advanced Configuration and Power Interface)** — defines device power states (D0-D3), processor states (C0-Cn), and performance states (P0-Pn). Even on ARM, many SoCs adopt ACPI-like abstractions.
- **PM QoS** — a kernel framework that lets drivers and applications specify latency and throughput requirements, preventing the PM subsystem from entering states that violate constraints.
- **Linux PM Core** — the kernel's central dispatcher that coordinates idle, suspend-to-RAM, and frequency scaling across all devices.

## Key Commands / Configuration / Code

### 1. Inspecting current power states and governors

```bash
# Show available CPU governors and current governor per core
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Show available sleep states (C-states) and their names
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/name

# Show latency for each C-state (microseconds)
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/latency
```

### 2. Checking PM QoS constraints

```bash
# View current PM QoS resume latency constraints for CPUs
cat /sys/devices/system/cpu/cpu0/power/pm_qos_resume_latency_us

# View device-level PM QoS constraints
cat /sys/class/drm/card0/device/power/pm_qos_resume_latency_us
```

### 3. Reading ACPI tables (x86 example, but concept applies)

```bash
# Dump the DSDT (Differentiated System Description Table)
# This shows all device power states and methods
sudo cat /sys/firmware/acpi/tables/DSDT > dsdt.dat
iasl -d dsdt.dat   # Decompile to human-readable ASL
```

### 4. Simple C snippet to enforce a latency constraint via PM QoS

```c
#include <linux/pm_qos.h>
#include <linux/device.h>

/* Request that the CPU never enter a state with > 50 us wake latency */
static struct pm_qos_request my_latency_req;

void set_latency_constraint(void) {
    pm_qos_add_request(&my_latency_req, PM_QOS_CPU_DMA_LATENCY, 50);
}

void remove_latency_constraint(void) {
    pm_qos_remove_request(&my_latency_req);
}
```

This is exactly how audio drivers prevent crackling by blocking deep C-states during playback.

## Common Pitfalls & Gotchas

1. **Assuming "idle" means zero power** — Many engineers think an idle CPU consumes negligible power. In reality, an ARM Cortex-A53 at idle in C0 can draw 50-100 mW. Always check the actual C-state residency using `cpuidle` counters, not just the governor name.

2. **PM QoS constraints that are too tight** — Setting a 0 µs latency constraint (common in audio drivers) forces the CPU to stay in C0, burning power constantly. The correct approach is to set the *minimum acceptable* latency, not the *minimum possible*. Measure your actual tolerance.

3. **Ignoring thermal coupling** — Power management and thermal management are not independent. A governor that aggressively races to idle may cause a thermal spike that throttles the CPU *after* the work is done, wasting the energy you tried to save. Always profile temperature alongside power.

## Try It Yourself

1. **Profile your system's idle residency** — On any Linux system (x86 or ARM), run `cpuidle` for 10 seconds of idle: `cat /sys/devices/system/cpu/cpu0/cpuidle/state*/usage`. Which state has the highest residency? What is the latency of that state?

2. **Test the impact of a PM QoS constraint** — Write a small kernel module (or use `devmem2` to poke the PM QoS sysfs) to set a 100 µs latency constraint. Then re-run the residency check. How did the distribution change?

3. **Compare governors** — Switch the CPU governor from `powersave` to `performance` while running a fixed workload (e.g., `stress --cpu 1 --timeout 30`). Measure total energy using `perf stat --power-avg` or an external power monitor. What's the energy difference for the same work?

## Next Up

Tomorrow I'll dive into the **Linux PM Stack: PM Core, Drivers & Governors** — how the kernel orchestrates idle, frequency scaling, and device suspend, and how to write a custom governor that respects real-time constraints without wasting energy.
