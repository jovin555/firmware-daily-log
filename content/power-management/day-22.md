---
title: "Day 22: Runtime PM: dev_pm_ops & rpm_suspend/resume"
date: 2026-07-04
tags: ["til", "power-management", "runtime-pm", "dev-pm-ops"]
---

## What I Explored Today

Today I dug into the actual mechanics of Runtime PM at the driver level — specifically how `dev_pm_ops` hooks into the runtime suspend/resume cycle, and what happens when the kernel calls `rpm_suspend()` or `rpm_resume()` on a device. I’ve been using Runtime PM for a while with `pm_runtime_put_sync()` and `pm_runtime_get_sync()`, but I never fully traced the callback chain. Today I instrumented a UART driver on an i.MX8M Mini to see exactly when `runtime_suspend` fires, what state the device is in, and how the autosuspend timer interacts with the core. The key insight: the `dev_pm_ops` structure is the contract between your driver and the PM core, and getting the return values wrong can silently break power savings.

## The Core Concept

Runtime PM isn’t magic — it’s a state machine managed by the PM core, and your driver provides the callbacks that actually toggle hardware power. The core handles the refcounts, timers, and synchronization; your driver handles the register writes, clock gating, and power rail sequencing.

The `dev_pm_ops` structure contains `runtime_suspend`, `runtime_resume`, and `runtime_idle` callbacks. When the last usage counter drops to zero (or the autosuspend delay expires), the core calls `rpm_idle()` first. If that returns 0 or the driver doesn’t provide it, the core proceeds to `rpm_suspend()`, which invokes your `runtime_suspend` callback. On resume, `rpm_resume()` calls your `runtime_resume` callback.

The critical detail: `rpm_suspend()` and `rpm_resume()` are internal PM core functions, not driver APIs. You never call them directly — you use `pm_runtime_put_sync()` / `pm_runtime_get_sync()` (or their async variants), which internally call `rpm_suspend`/`rpm_resume`. The core also handles the `RPM_SUSPENDED`, `RPM_RESUMING`, `RPM_SUSPENDING` state transitions, and will refuse to suspend if a resume is in progress.

## Key Commands / Configuration / Code

### 1. Defining the callbacks in `dev_pm_ops`

```c
#include <linux/pm_runtime.h>

static int my_uart_runtime_suspend(struct device *dev)
{
    struct uart_port *port = dev_get_drvdata(dev);
    struct my_uart_data *data = port->private_data;

    dev_dbg(dev, "Runtime suspend: gating clocks\n");
    clk_disable_unprepare(data->clk_uart);
    clk_disable_unprepare(data->clk_ipg);
    return 0;  // Must return 0 on success, -EAGAIN to retry, -EBUSY to abort
}

static int my_uart_runtime_resume(struct device *dev)
{
    struct uart_port *port = dev_get_drvdata(dev);
    struct my_uart_data *data = port->private_data;
    int ret;

    dev_dbg(dev, "Runtime resume: ungating clocks\n");
    ret = clk_prepare_enable(data->clk_ipg);
    if (ret)
        return ret;
    ret = clk_prepare_enable(data->clk_uart);
    if (ret) {
        clk_disable_unprepare(data->clk_ipg);
        return ret;
    }
    return 0;
}

static int my_uart_runtime_idle(struct device *dev)
{
    dev_dbg(dev, "Runtime idle: allowing suspend\n");
    return 0;  // Return 0 to allow immediate suspend, -EBUSY to defer
}

static const struct dev_pm_ops my_uart_pm_ops = {
    RUNTIME_PM_OPS(my_uart_runtime_suspend,
                   my_uart_runtime_resume,
                   my_uart_runtime_idle)
    // Also define system PM ops if needed:
    // SET_SYSTEM_SLEEP_PM_OPS(pm_runtime_force_suspend,
    //                         pm_runtime_force_resume)
};
```

### 2. Enabling Runtime PM in probe

```c
static int my_uart_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    int ret;

    // ... hardware init ...

    pm_runtime_set_autosuspend_delay(dev, 100);  // 100ms delay
    pm_runtime_use_autosuspend(dev);
    pm_runtime_set_active(dev);   // Mark device as active (count = 1)
    pm_runtime_enable(dev);       // Enable runtime PM for this device

    // After probe, release the initial reference:
    pm_runtime_put_autosuspend(dev);

    return 0;
}

static int my_uart_remove(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;

    pm_runtime_get_sync(dev);     // Ensure device is active before teardown
    pm_runtime_dont_use_autosuspend(dev);
    pm_runtime_disable(dev);

    // ... hardware teardown ...
    return 0;
}
```

### 3. Tracing the state machine

```bash
# Enable Runtime PM debugfs
mount -t debugfs none /sys/kernel/debug
echo 1 > /sys/kernel/debug/pm_debug/enable

# Check device runtime status
cat /sys/devices/platform/3002000.uart/power/runtime_status
# Output: suspended | active | suspending | resuming

# Check usage counter
cat /sys/devices/platform/3002000.uart/power/runtime_usage
# Output: 0 (suspended) or >0 (active)

# Force a suspend/resume cycle for testing
echo auto > /sys/devices/platform/3002000.uart/power/control
echo on > /sys/devices/platform/3002000.uart/power/control  # force resume
```

### 4. Key return value semantics

```c
// In your runtime_suspend callback:
//  0       -> suspend succeeded, device enters RPM_SUSPENDED
//  -EAGAIN -> suspend failed, core will retry later (e.g., if clock not ready)
//  -EBUSY  -> suspend aborted, device stays RPM_ACTIVE
//  -EINPROGRESS -> asynchronous suspend started, core waits for completion

// In your runtime_resume callback:
//  0       -> resume succeeded, device enters RPM_ACTIVE
//  -EAGAIN -> resume failed, core retries
//  -EBUSY  -> resume failed, device stays RPM_SUSPENDED
```

## Common Pitfalls & Gotchas

1. **Forgetting `pm_runtime_set_active()` before `pm_runtime_enable()`**  
   If you call `pm_runtime_enable()` with the device in the default `RPM_SUSPENDED` state, the first `pm_runtime_get_sync()` will call your `runtime_resume` callback — even if the hardware is already powered on. This can cause double-enable of clocks or regulators. Always set the initial state explicitly.

2. **Returning wrong error codes from callbacks**  
   Returning `-ENODEV` or `-EIO` from `runtime_suspend` is treated as a suspend failure, but the core will keep retrying indefinitely. Use `-EBUSY` to abort cleanly, or `-EAGAIN` for transient failures. I once spent two hours debugging why a device never suspended — the driver returned `-EAGAIN` from `runtime_idle` instead of 0.

3. **Not handling autosuspend vs. immediate suspend correctly**  
   If you use `pm_runtime_put_sync()` (immediate) instead of `pm_runtime_put_autosuspend()`, the device suspends right away, which can cause thrashing if the device is used frequently. Always prefer autosuspend for I/O devices. The autosuspend timer starts when the usage count drops to zero; if a new get arrives before the timer fires, the suspend is cancelled.

## Try It Yourself

1. **Instrument a UART or I2C driver** — Add `dev_dbg()` calls in your `runtime_suspend` and `runtime_resume` callbacks. Enable dynamic debug and watch the trace as you open/close the device. Verify the callback fires only when the usage count hits zero.

2. **Test autosuspend behavior** — Set a 500ms autosuspend delay, then rapidly open/close the device every 100ms. Check `/sys/kernel/debug/pm_debug/time` to see if the device ever suspends. Then increase the delay to 2 seconds and repeat — the device should never suspend during the rapid open/close cycle.

3. **Force a suspend failure** — Modify your `runtime_suspend` callback to return `-EBUSY` if a certain condition is met (e.g., a sysfs flag). Verify that the device stays in `RPM_ACTIVE` and that `runtime_status` never transitions to `suspended`. Check `runtime_error` in sysfs to see the error count increment.

## Next Up

Tomorrow: **Wakeup Sources: Configuring & Debugging Wakeup Events** — we’ll look at how to make a suspended device wake the system, using `device_init_wakeup()`, `pm_wakeup_event()`, and the wakeup IRQ framework. We’ll also debug wakeup sources with `wakeup_count` and `pm_print_active_wakeup_sources()`.
