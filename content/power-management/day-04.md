---
title: "Day 04: Runtime PM: dev_pm_ops & rpm_suspend/resume"
date: 2026-06-16
tags: ["til", "power-management", "runtime-pm", "dev-pm-ops"]
---

## What I Explored Today

Today I dug into the actual machinery of Runtime Power Management (Runtime PM) in the Linux kernel: the `dev_pm_ops` structure and the core `rpm_suspend()`/`rpm_resume()` functions. While yesterday we enabled Runtime PM at the bus or driver level, today I wanted to understand exactly what callbacks get invoked, in what order, and how the kernel decides whether to suspend or resume a device. I traced through the kernel source (drivers/base/power/runtime.c) and instrumented a real I2C touch controller driver to watch the transitions.

## The Core Concept

Runtime PM is fundamentally about *opportunistic* power savings. Unlike system-wide suspend (suspend-to-RAM or hibernation), Runtime PM lets individual devices enter low-power states when idle, without affecting the rest of the system. The key insight is that **the device must be in a state where it can be resumed quickly** — typically microseconds to milliseconds — because the next access might come from an unrelated driver or interrupt.

The `dev_pm_ops` structure is the contract between a driver and the PM core. It contains both system-level callbacks (`.suspend`, `.resume`) and runtime-specific callbacks (`.runtime_suspend`, `.runtime_resume`, `.runtime_idle`). The runtime callbacks are the ones that matter for our daily work. The core functions `rpm_suspend()` and `rpm_resume()` handle the state machine: they check usage counts, prevent races with system suspend, and invoke the driver callbacks at the right moment.

The critical detail: **`rpm_suspend()` does not automatically call your driver's callback**. It first checks the device's usage counter (`usage_count`), the runtime PM status (` RPM_ACTIVE`, ` RPM_SUSPENDED`, ` RPM_SUSPENDING`), and any pending requests. Only if the device is truly idle and no one has taken a reference does it proceed to call `dev->pm_domain->ops.runtime_suspend()` or `dev->type->pm.runtime_suspend()` or `dev->driver->pm->runtime_suspend()`, in that priority order.

## Key Commands / Configuration / Code

### 1. The `dev_pm_ops` structure for a driver

```c
// From include/linux/pm.h
struct dev_pm_ops {
    // System-level (not our focus today)
    int (*suspend)(struct device *dev);
    int (*resume)(struct device *dev);
    // Runtime PM callbacks
    int (*runtime_suspend)(struct device *dev);
    int (*runtime_resume)(struct device *dev);
    int (*runtime_idle)(struct device *dev);
};
```

### 2. Minimal driver implementation

```c
// Example: I2C touch controller runtime PM callbacks
static int touch_runtime_suspend(struct device *dev)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct touch_data *data = i2c_get_clientdata(client);

    dev_dbg(dev, "Runtime suspend: disabling IRQ, powering off\n");
    disable_irq(client->irq);           // Prevent wake from our own IRQ
    regmap_write(data->regmap, 0x10, 0x00); // Put chip into sleep mode
    return 0;
}

static int touch_runtime_resume(struct device *dev)
{
    struct i2c_client *client = to_i2c_client(dev);
    struct touch_data *data = i2c_get_clientdata(client);

    dev_dbg(dev, "Runtime resume: powering on, enabling IRQ\n");
    regmap_write(data->regmap, 0x10, 0x01); // Wake chip
    enable_irq(client->irq);                // Re-enable interrupt
    return 0;
}

// Assign to the driver's PM ops
static const struct dev_pm_ops touch_pm_ops = {
    RUNTIME_PM_OPS(touch_runtime_suspend,
                   touch_runtime_resume,
                   NULL)  // runtime_idle (optional)
};

// In the I2C driver structure
static struct i2c_driver touch_driver = {
    .driver = {
        .name = "touch_controller",
        .pm = pm_ptr(&touch_pm_ops),  // pm_ptr() handles CONFIG_PM=n
    },
    .probe = touch_probe,
    .id_table = touch_ids,
};
```

### 3. Triggering runtime suspend/resume manually (debugging)

```bash
# Check current runtime PM status for a device
cat /sys/devices/platform/soc/XXXX.i2c/i2c-X/X-XXXX/power/runtime_status

# Force a suspend (if autosuspend is enabled)
echo 0 > /sys/devices/.../power/control   # Set to "on" (disable runtime PM)
echo auto > /sys/devices/.../power/control # Re-enable runtime PM

# Manually trigger a suspend/resume cycle
echo 0 > /sys/devices/.../power/runtime_suspended_time_ns  # Reset counter
# Wait for autosuspend delay, or force:
echo 1 > /sys/devices/.../power/runtime_usage  # Take a reference (prevents suspend)
echo 0 > /sys/devices/.../power/runtime_usage  # Release reference
```

### 4. Kernel tracepoint for runtime PM transitions

```bash
# Trace all runtime PM events for a specific device
echo 'rpm:*' > /sys/kernel/debug/tracing/set_event
echo 1 > /sys/kernel/debug/tracing/tracing_on
cat /sys/kernel/debug/tracing/trace_pipe

# You'll see lines like:
# rpm_suspend: device=XXXX.i2c, state=0 -> 2 (RPM_ACTIVE -> RPM_SUSPENDING)
# rpm_return_int: ret=0
# rpm_resume: device=XXXX.i2c, state=2 -> 0 (RPM_SUSPENDING -> RPM_ACTIVE)
```

## Common Pitfalls & Gotchas

### 1. **Forgetting to balance `pm_runtime_get()`/`pm_runtime_put()`**
Every `pm_runtime_get_sync()` must have a matching `pm_runtime_put()` or `pm_runtime_put_autosuspend()`. If you leak a reference, the device will never suspend. I've seen this cause 200mW extra power drain in a production tablet. Use `pm_runtime_get_noresume()` + `pm_runtime_put_noidle()` for atomic contexts where you can't sleep.

### 2. **Interrupts firing during runtime suspend/resume**
If your `runtime_suspend` callback disables the device's IRQ, make sure you do it *before* putting the hardware to sleep. Otherwise, an interrupt can arrive while the device is partially suspended, causing a resume race or a lockup. Always disable the IRQ first, then write the sleep command to the hardware.

### 3. **`runtime_idle` callback is not mandatory, but you probably want it**
The kernel calls `runtime_idle` when the device's usage count drops to zero. If you don't implement it, the PM core will schedule an autosuspend after the delay. But if you *do* implement it, you can return `-EBUSY` to prevent suspend if you know the device will be used again soon. This is useful for devices with high resume latency.

## Try It Yourself

1. **Instrument a driver with tracepoints**: Pick a device on your system (e.g., an I2C touch controller or a USB HID device). Enable runtime PM tracepoints and watch the suspend/resume cycle as you touch the screen or move the mouse. Note the latency between the last event and the suspend.

2. **Force a runtime PM cycle manually**: For a device that supports runtime PM, write `auto` to `power/control`, then use `cat /sys/kernel/debug/pm_debug/devices` to see the device's state. Use `echo 0 > power/runtime_usage` to release any lingering references and trigger suspend.

3. **Write a minimal driver with custom `runtime_suspend`/`runtime_resume`**: If you have a development board, create a platform driver that toggles a GPIO in the runtime callbacks. Use `pm_runtime_autosuspend()` with a 1-second delay and verify the GPIO state changes as expected.

## Next Up

Tomorrow we tackle **Wakeup Sources: Configuring & Debugging Wakeup Events**. We'll explore how to make devices wake the system from suspend, the `wakeup_source` framework, and how to debug "why won't my device wake up?" using `/sys/power/wakeup_count` and `pm_wakeup_event()`.
