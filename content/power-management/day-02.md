---
title: "Day 02: Linux PM Stack: PM Core, Drivers & Governors"
date: 2026-06-14
tags: ["til", "power-management", "linux-pm", "pm-core", "drivers"]
---

## What I Explored Today

Today I dug into the Linux Power Management (PM) stack — specifically how the PM Core, device drivers, and CPU frequency governors interact to control power consumption. I traced the path from a `cpufreq` governor decision down through the driver layer, and examined the sysfs and debugfs interfaces that expose this machinery. The key insight: the PM stack is a layered architecture where policy (governors) sits above hardware abstraction (drivers), with the PM Core providing the glue and notification mechanisms.

## The Core Concept

The Linux PM stack exists because power management is inherently cross-cutting. A single decision — "should this CPU run at 1.2 GHz or 800 MHz?" — involves:

1. **Policy**: What's the system's current power/performance trade-off? (governor)
2. **Capability**: What frequencies does this hardware actually support? (driver)
3. **Coordination**: How do we notify other subsystems (thermal, scheduler, device drivers) when a frequency changes? (PM Core)

Without this layered design, every driver would need to know about every governor, and every governor would need hardware-specific frequency tables. The PM Core abstracts this: governors call generic APIs like `cpufreq_driver_target()`, which the core dispatches to the appropriate driver callback. The core also handles locking, notifies registered listeners via `cpufreq_notify_transition()`, and manages sysfs attributes.

The real power of this design is that you can swap governors at runtime without touching a single line of driver code — and vice versa, you can port a driver to a new SoC without rewriting the governor logic.

## Key Commands / Configuration / Code

### 1. Inspecting the Governor and Driver Stack

```bash
# See current governor and available governors for CPU0
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors

# See the underlying driver and hardware limits
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq

# Available frequencies (hardware-supported)
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies
```

### 2. Changing the Governor at Runtime

```bash
# Switch to performance governor (max frequency always)
echo performance | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Switch to powersave governor (min frequency always)
echo powersave | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Switch to ondemand (ramp up on load, down on idle)
echo ondemand | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Apply to all CPUs
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo ondemand | sudo tee "$cpu"
done
```

### 3. Driver Registration (Kernel Code Snippet)

This is how a cpufreq driver registers with the PM Core. Real example from `drivers/cpufreq/imx6q-cpufreq.c`:

```c
static struct cpufreq_driver imx6q_cpufreq_driver = {
    .flags      = CPUFREQ_NEED_INITIAL_FREQ_CHECK,
    .verify     = imx6q_cpufreq_verify,
    .target     = imx6q_cpufreq_target,  // Called by core when governor requests freq change
    .get        = imx6q_cpufreq_get,
    .init       = imx6q_cpufreq_init,
    .exit       = imx6q_cpufreq_exit,
    .name       = "imx6q-cpufreq",
    .attr       = cpufreq_generic_attr,
};

static int __init imx6q_cpufreq_init_module(void)
{
    return cpufreq_register_driver(&imx6q_cpufreq_driver);
}
module_init(imx6q_cpufreq_init_module);
```

The governor calls `__cpufreq_driver_target()` in the core, which acquires the mutex and calls `driver->target(policy, target_freq, relation)`. The driver then programs the hardware clock dividers or PMIC voltage regulators.

### 4. Debugging with ftrace

```bash
# Trace cpufreq transitions in real-time
echo 'cpufreq:*' > /sys/kernel/debug/tracing/set_event
cat /sys/kernel/debug/tracing/trace_pipe

# Sample output:
# cpufreq_frequency_change: cpu=0, old_freq=800000, new_freq=1200000
# cpufreq_interactive_target: cpu=0, load=85, cur=800000, target=1200000
```

## Common Pitfalls & Gotchas

### 1. Governor Doesn't Stick After Resume
Many embedded systems lose the governor setting after suspend/resume because the PM Core reinitializes the cpufreq policy during resume. Always set the governor in a late resume hook or via a udev rule triggered on `change` events for the cpufreq sysfs files. The `ondemand` and `conservative` governors are especially prone to this because they have internal state (load tracking) that gets reset.

### 2. Thermal Throttling Overrides Governor Decisions
The `cpufreq` governor is not the final authority on frequency. The thermal framework (`thermal_sys`) can cap frequencies via `cpufreq_cooling` — even if your governor says "run at 1.5 GHz," the thermal driver can force 800 MHz. Check `/sys/class/thermal/thermal_zone*/policy` and `cpufreq` sysfs simultaneously to see if throttling is active. I've spent hours debugging "why is my performance governor not working?" only to find a thermal zone at 85°C.

### 3. Shared Frequency Domains (Clusters)
On ARM big.LITTLE and similar architectures, multiple CPUs share a single voltage/frequency domain. Changing frequency for one CPU affects all CPUs in that cluster. The governor's `policy->cpus` mask shows which CPUs are coupled. Writing to `scaling_setspeed` on one CPU while another in the same cluster is busy can cause performance anomalies — the kernel serializes this, but you'll see all CPUs transition together in ftrace.

## Try It Yourself

1. **Governor Impact Measurement**: On your embedded Linux board (Raspberry Pi, BeagleBone, etc.), run a CPU-intensive task (e.g., `openssl speed -multi 4`) under the `powersave` governor, then under `performance`. Measure elapsed time and power consumption (if you have a current monitor). Record the frequency transitions using `cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq` every second.

2. **Driver Discovery**: Find which cpufreq driver your system uses (`scaling_driver`). Then look at the kernel source for that driver (e.g., `drivers/cpufreq/`). Identify the `.target` callback and trace its call path using ftrace with `echo 'cpufreq:*' > /sys/kernel/debug/tracing/set_event`. Note how many times the frequency changes during a 30-second idle period.

3. **Governor Swap Stress Test**: Write a shell script that switches the governor every 5 seconds between `ondemand`, `conservative`, `powersave`, and `performance` while running a background CPU load. Check `/proc/interrupts` to see if any timer interrupts increase (governors use timers for load sampling). Verify no kernel warnings appear in `dmesg`.

## Next Up

Tomorrow: **System Sleep States in Linux** — we'll explore the suspend/resume subsystem: `mem`, `standby`, `freeze`, and how drivers implement `suspend()`/`resume()` callbacks. I'll show you how to debug a driver that fails to resume, and the exact path from `echo mem > /sys/power/state` to the hardware's deep sleep mode.
