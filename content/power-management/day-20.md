---
title: "Day 20: Linux PM Stack: PM Core, Drivers & Governors"
date: 2026-07-02
tags: ["til", "power-management", "linux-pm", "pm-core", "drivers"]
---

## What I Explored Today

Today I dug into the Linux Power Management (PM) stack, specifically how the PM Core, device drivers, and governors interact to manage system-wide and per-device power states. The kernel's PM subsystem is not a monolithic block—it's a layered architecture where the PM Core provides the framework, drivers implement the hardware-specific callbacks, and governors make policy decisions about when to enter which state. I traced through the `struct dev_pm_ops`, examined how `pm_runtime_put_sync()` triggers runtime suspend, and benchmarked how the `ondemand` vs `performance` CPUfreq governors affect idle power draw on an i.MX8M Plus board.

## The Core Concept

The Linux PM stack exists because hardware power management is inherently device-specific, but the *policy* for when to save power should be generic. The PM Core solves this by providing:

- **A common callback interface** (`struct dev_pm_ops`) that every driver must implement for suspend/resume transitions.
- **A state machine** (active, suspending, suspended, resuming) that prevents race conditions.
- **A notification chain** so subsystems (like PCI, USB, I2C) can coordinate power transitions.

Drivers are the "doers"—they know how to toggle clocks, gate power rails, or save/restore register context. Governors are the "deciders"—they observe system load, battery level, or thermal limits and tell the PM Core which state to target. The separation means you can swap a governor (e.g., `powersave` vs `performance`) without touching a single driver, and you can add a new driver without modifying the PM Core.

The real engineering insight: **the PM Core is a framework for coordination, not optimization**. It ensures that when the CPU enters idle, all dependent devices (e.g., DMA engines, GPIO banks) are suspended in the correct order. Without this, a device might be powered off while its interrupt line is still asserted, causing spurious wakeups or lockups.

## Key Commands / Configuration / Code

### 1. Inspecting the PM Core callbacks for a device

```bash
# List all devices and their PM capabilities (runtime status, control)
find /sys/devices -name "power" -type d | head -5 | while read d; do
    echo "=== $d ==="
    cat $d/control      # auto/on/off
    cat $d/runtime_status  # active/suspended/suspending
    cat $d/runtime_usage   # usage count (0 = can suspend)
done

# Check a specific driver's PM ops (example: I2C controller)
cat /sys/bus/platform/drivers/fsl-imx-i2c/*/power/runtime_status
```

### 2. Driver PM ops structure (kernel code snippet)

```c
// From include/linux/pm.h
struct dev_pm_ops {
    int (*prepare)(struct device *dev);
    void (*complete)(struct device *dev);
    int (*suspend)(struct device *dev);
    int (*resume)(struct device *dev);
    int (*runtime_suspend)(struct device *dev);
    int (*runtime_resume)(struct device *dev);
    int (*runtime_idle)(struct device *dev);
};

// Example: minimal I2C driver with runtime PM
static const struct dev_pm_ops my_i2c_pm_ops = {
    SET_SYSTEM_SLEEP_PM_OPS(my_i2c_suspend, my_i2c_resume)
    SET_RUNTIME_PM_OPS(my_i2c_runtime_suspend,
                       my_i2c_runtime_resume,
                       my_i2c_runtime_idle)
};
```

### 3. CPUfreq governor interaction

```bash
# Current governor and available ones
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors

# Switch governor and measure idle power delta
echo "powersave" > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
# Wait 10 seconds, then read power rail
cat /sys/class/power_supply/regulator*/power_now   # μW

echo "performance" > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
# Compare: powersave typically saves 15-30% at idle
```

### 4. Runtime PM manual control for debugging

```bash
# Force a device into runtime suspend (if autosuspend is off)
echo "on" > /sys/devices/.../power/control   # disable runtime PM
echo "auto" > /sys/devices/.../power/control  # re-enable

# Manually trigger suspend/resume (requires driver support)
echo 0 > /sys/devices/.../power/runtime_usage  # decrement usage count
cat /sys/devices/.../power/runtime_status       # should show "suspended"
```

## Common Pitfalls & Gotchas

1. **Governor ≠ Driver PM state**: Changing the CPUfreq governor to `powersave` does *not* automatically suspend peripherals. The governor only controls CPU P-states. To save power on an I2C sensor, you must either use runtime PM (driver calls `pm_runtime_put_sync()`) or system suspend. I once saw a team spend days debugging "why powersave doesn't reduce power"—they forgot to enable runtime PM on their SPI display driver.

2. **Runtime PM reference counting leaks**: Every `pm_runtime_get_sync()` must be paired with a `pm_runtime_put_sync()`. If a driver calls `get` in an interrupt handler but forgets the `put`, the device will never suspend. Use `pm_runtime_get_noresume()` + `pm_runtime_put_noidle()` for atomic contexts. Check with:
   ```bash
   cat /sys/devices/.../power/runtime_usage  # should be 0 at idle
   ```

3. **Order of operations in suspend/resume callbacks**: The PM Core calls `suspend` from leaf devices to root (children first, then parent). `resume` is the reverse. If your driver assumes the parent clock is still running during `suspend`, you'll get a lockup. Always save register context *before* disabling the parent clock, and restore *after* re-enabling it.

## Try It Yourself

1. **Trace a driver's PM callbacks**: Pick a device on your board (e.g., an I2C touch controller). Enable dynamic debug for PM: `echo 'file drivers/base/power/runtime.c +p' > /sys/kernel/debug/dynamic_debug/control`. Then trigger runtime suspend by disabling the device's autosuspend timer: `echo 0 > /sys/devices/.../power/autosuspend_delay_ms`. Watch the kernel log for `__rpm_callback` entries.

2. **Measure governor impact on idle power**: Use a power monitor (or the board's built-in ADC) to measure total system power at idle with `powersave` vs `performance` governors. Record the delta. Then add a `cpuidle` governor change: `echo "menu" > /sys/devices/system/cpu/cpuidle/current_governor`. Re-measure. The `menu` governor typically adds 5-10% savings by predicting idle duration.

3. **Write a minimal driver with runtime PM**: Create a kernel module that registers a platform device with `SET_RUNTIME_PM_OPS`. In `runtime_suspend`, toggle a GPIO to indicate "sleeping". In `runtime_resume`, toggle it back. Load the module, then manually trigger suspend via sysfs. Verify the GPIO state changes.

## Next Up

Tomorrow: **Suspend/Resume: System Sleep States in Linux** — we'll dissect the `mem`, `standby`, and `freeze` states, learn how `pm_test` can validate your suspend path without actually entering sleep, and debug a real-world case where a USB controller prevented S2RAM from working.
