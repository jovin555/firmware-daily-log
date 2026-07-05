---
title: "Day 23: Wakeup Sources: Configuring & Debugging Wakeup Events"
date: 2026-07-05
tags: ["til", "power-management", "wakeup", "wakelock"]
---

## What I Explored Today

Today I dove into the kernel's wakeup source infrastructure — the mechanism that decides whether a system can enter a sleep state and what can bring it back. I traced through `drivers/base/power/wakeup.c`, tested wakeup counts on a BeagleBone Black, and deliberately misconfigured a GPIO to trigger a wakeup storm. The key takeaway: wakeup sources are not just "interrupts that work during sleep" — they are reference-counted, kernel-managed objects that gate the entire suspend path.

## The Core Concept

A wakeup source is a kernel object (`struct wakeup_source`) that tracks whether a device or subsystem has the ability to wake the system from a sleep state. Every wakeup-capable device driver must register one. The core logic is simple: during suspend, the PM core checks `wakeup_source->active`. If any wakeup source is active (i.e., a wake event is being processed), the suspend is aborted. This prevents the system from going to sleep while a wakeup event is still being handled — a classic race condition.

Why does this matter? Without wakeup sources, you get two failure modes:
1. **Spurious wakeups** — a device fires an interrupt during suspend, but the kernel has already committed to sleep, so the interrupt is lost or the system wakes immediately.
2. **Missed wakeups** — a device asserts a wake signal, but the kernel ignores it because the interrupt controller is already powered down.

Wakeup sources solve this by providing a **handshake**: the device driver calls `__pm_stay_awake()` before the interrupt handler finishes, and `__pm_relax()` when the event is fully processed. The PM core waits until all sources are inactive before finalizing suspend.

## Key Commands / Configuration / Code

### 1. Inspecting wakeup sources at runtime

```bash
# List all registered wakeup sources and their statistics
cat /sys/kernel/debug/wakeup_sources

# Example output (abbreviated):
# name                   active_count  event_count  wakeup_count  expire_count  active_since  total_time  max_time  last_time
# alarmtimer             0             0            0             0             0             0           0         0
# gpio-keys              0             12           12            0             0             1250        320       45
# mmc0                  0             0            0             0             0             0           0         0
```

The `event_count` vs `wakeup_count` distinction is critical: `event_count` increments on every wakeup event (even if the system was already awake), while `wakeup_count` only increments when the event actually wakes the system from sleep.

### 2. Enabling/disabling wakeup capability per device

```bash
# Check if a device can wake the system
cat /sys/devices/platform/ocp/44e07000.gpio/power/wakeup
# Output: "enabled" or "disabled"

# Enable wakeup for a GPIO controller
echo enabled > /sys/devices/platform/ocp/44e07000.gpio/power/wakeup

# Disable it
echo disabled > /sys/devices/platform/ocp/44e07000.gpio/power/wakeup
```

### 3. Kernel code: registering a wakeup source in a driver

```c
#include <linux/pm_wakeup.h>

static struct wakeup_source *ws;

static int my_probe(struct platform_device *pdev)
{
    // Create a wakeup source named "my_driver_wakeup"
    ws = wakeup_source_register(dev, "my_driver_wakeup");
    if (!ws)
        return -ENOMEM;

    // Mark device as wakeup-capable
    device_init_wakeup(dev, true);
    return 0;
}

static irqreturn_t my_irq_handler(int irq, void *data)
{
    // Prevent suspend while we process this event
    __pm_stay_awake(ws);

    // ... handle the interrupt ...

    // Allow suspend again
    __pm_relax(ws);
    return IRQ_HANDLED;
}

static int my_suspend(struct device *dev)
{
    // Enable the IRQ as a wakeup source
    enable_irq_wake(irq);
    return 0;
}

static int my_resume(struct device *dev)
{
    disable_irq_wake(irq);
    return 0;
}
```

### 4. Debugging wakeup storms with ftrace

```bash
# Trace wakeup source activity
echo 1 > /sys/kernel/debug/tracing/events/power/wakeup_source/enable
cat /sys/kernel/debug/tracing/trace_pipe

# Look for patterns like:
# <idle>-0     [000] d.s2   123.456: wakeup_source_activate: my_driver_wakeup state=0x1
# <idle>-0     [000] d.s3   123.457: wakeup_source_deactivate: my_driver_wakeup state=0x0
```

If you see rapid activate/deactivate cycles, you have a wakeup storm — the device is firing events faster than the driver can process them.

## Common Pitfalls & Gotchas

### 1. Forgetting `device_init_wakeup()`
I spent an hour debugging why `enable_irq_wake()` returned `-ENXIO`. The root cause: I registered the wakeup source but never called `device_init_wakeup(dev, true)`. Without this, the PM core doesn't know the device *can* wake, and `enable_irq_wake()` silently fails. Always call `device_init_wakeup()` in probe.

### 2. Wakeup source leak from unbalanced `__pm_stay_awake`/`__pm_relax`
If you call `__pm_stay_awake()` twice without matching `__pm_relax()` calls, the wakeup source stays active forever. The system will never suspend. I've seen this in production with interrupt handlers that have multiple return paths. Use a single point of `__pm_relax()` (e.g., at the end of the handler) and add `WARN_ON(ws->active > 1)` during development.

### 3. Confusing `event_count` and `wakeup_count`
A device that fires events while the system is awake will show a high `event_count` but zero `wakeup_count`. This is normal. But if you see `wakeup_count` incrementing rapidly during suspend attempts, you have a device that's preventing sleep. Check `active_since` — if it's non-zero, the wakeup source is stuck active.

## Try It Yourself

1. **Inspect your system's wakeup sources**: Run `cat /sys/kernel/debug/wakeup_sources` on an embedded board. Identify which devices have the highest `event_count`. Then trigger a suspend (`echo mem > /sys/power/state`) and check which `wakeup_count` values changed.

2. **Simulate a wakeup storm**: Write a small kernel module that registers a wakeup source and calls `__pm_stay_awake()` / `__pm_relax()` in a tight loop (every 10ms). Use ftrace to observe the activate/deactivate pattern. Try suspending — what happens?

3. **Misconfigure a GPIO wakeup**: On a Raspberry Pi or BeagleBone, enable wakeup on a GPIO that has a noisy input (e.g., a floating pin). Use `echo enabled > /sys/class/gpio/gpioN/power/wakeup` and attempt suspend. Check `dmesg` for "PM: Wakeup source XXX" messages. Fix by adding a pull-up/down resistor or debouncing in software.

## Next Up

Tomorrow: **cpufreq: Governors, Policies & DVFS on Embedded** — we'll move from sleep states to active power management, exploring how the CPU frequency scaling subsystem dynamically adjusts voltage and frequency, and why the `schedutil` governor is often the right choice for latency-sensitive embedded workloads.
