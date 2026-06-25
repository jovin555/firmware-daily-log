---
title: "Day 13: Zephyr Power Management: pm_state & Device PM"
date: 2026-06-25
tags: ["til", "power-management", "zephyr", "pm-state", "device-pm"]
---

## What I Explored Today

Today I dug into Zephyr's power management subsystem, specifically how `pm_state` defines system sleep states and how Device PM controls individual peripherals. I've been putting off this deep dive because the API surface looked intimidating, but after tracing through the idle thread and a few driver PM callbacks, the architecture is actually elegant. The key insight: Zephyr separates *system-level* sleep states (what the CPU and RAM do) from *device-level* power states (what each peripheral does), and you must configure both correctly to achieve real power savings.

## The Core Concept

Most embedded engineers think "power management" means just calling `WFI` in the idle loop. That's wrong. Zephyr's PM framework is a two-layer cake:

**Layer 1: System PM (`pm_state`)**  
These are the CPU-level sleep states defined in `pm/state.h`. Each state has a power consumption level, a residency requirement (minimum time to make the state worthwhile), and a wake-up latency. The states are:

- `PM_STATE_ACTIVE` — CPU running, no sleep
- `PM_STATE_STANDBY` — Core clock gated, RAM retained, fast wake (microseconds)
- `PM_STATE_SUSPEND_TO_IDLE` — Deeper sleep, RAM retained, wake latency ~100µs
- `PM_STATE_SUSPEND_TO_RAM` — RAM self-refresh, CPU powered down, wake ~ms
- `PM_STATE_SUSPEND_TO_DISK` — Full power off, context saved to non-volatile

The Zephyr idle thread automatically selects the deepest allowed state based on the next timer interrupt. You control this via `pm_state_cpu_get_all()` and `pm_notifier_register()`.

**Layer 2: Device PM**  
This is per-driver power management. Each device driver can implement `pm_control()` callbacks to handle transitions between:
- `PM_DEVICE_STATE_ACTIVE` — fully powered
- `PM_DEVICE_STATE_SUSPEND` — low power, context may be lost
- `PM_DEVICE_STATE_OFF` — power removed, full reinit needed

The magic happens when system PM transitions: before entering `PM_STATE_SUSPEND_TO_RAM`, Zephyr calls `pm_device_state_set()` on every device that registered a PM action. After wake, it restores them.

## Key Commands / Configuration / Code

### 1. Enabling PM in your project

```kconfig
# prj.conf — must have these
CONFIG_PM=y
CONFIG_PM_DEVICE=y
CONFIG_PM_DEVICE_RUNTIME=y   # enables per-device runtime PM
CONFIG_SYS_CLOCK_TICKS_PER_SEC=100  # lower tick rate = deeper idle
```

### 2. Defining system PM constraints

```c
/* main.c — prevent deep sleep during critical operations */
#include <zephyr/pm/pm.h>
#include <zephyr/pm/state.h>

void critical_section_start(void)
{
    /* Block all states deeper than STANDBY */
    pm_state_exit_post_ops(PM_STATE_STANDBY, PM_STATE_SUSPEND_TO_IDLE);
}

void critical_section_end(void)
{
    /* Re-allow deeper states */
    pm_state_exit_post_ops(PM_STATE_SUSPEND_TO_RAM, PM_STATE_SUSPEND_TO_RAM);
}
```

### 3. Device PM callback implementation

```c
/* drivers/sensor/my_sensor.c — device PM handler */
#include <zephyr/pm/device.h>

static int my_sensor_pm_action(const struct device *dev,
                               enum pm_device_action action)
{
    switch (action) {
    case PM_DEVICE_ACTION_SUSPEND:
        /* Save context, turn off sensor */
        my_sensor_reg_save(dev);
        gpio_pin_set(sensor_enable_gpio, 0);
        break;
    case PM_DEVICE_ACTION_RESUME:
        /* Restore context, re-init sensor */
        gpio_pin_set(sensor_enable_gpio, 1);
        k_sleep(K_MSEC(10));  /* sensor power-up delay */
        my_sensor_reg_restore(dev);
        break;
    case PM_DEVICE_ACTION_TURN_OFF:
        /* Full power down, no context save needed */
        gpio_pin_set(sensor_enable_gpio, 0);
        break;
    default:
        return -ENOTSUP;
    }
    return 0;
}

PM_DEVICE_DEFINE(my_sensor, my_sensor_pm_action);
```

### 4. Runtime PM for a UART that's mostly idle

```c
/* In application code — put UART to sleep when not in use */
#include <zephyr/pm/device.h>
#include <zephyr/drivers/uart.h>

const struct device *uart_dev = DEVICE_DT_GET(DT_NODELABEL(uart0));

void send_burst(const uint8_t *data, size_t len)
{
    pm_device_action_run(uart_dev, PM_DEVICE_ACTION_RESUME);
    for (size_t i = 0; i < len; i++) {
        uart_poll_out(uart_dev, data[i]);
    }
    pm_device_action_run(uart_dev, PM_DEVICE_ACTION_SUSPEND);
}
```

### 5. Measuring actual state transitions

```bash
# Build with PM stats enabled
west build -b nrf52840dk_nrf52840 -t menuconfig
# Enable CONFIG_PM_STATS=y under Power Management

# After flashing, check via shell
uart:~$ pm stats
State                    Count    Residency(us)
PM_STATE_ACTIVE          1        12345678
PM_STATE_STANDBY         42       234567
PM_STATE_SUSPEND_TO_IDLE 15       89012
```

## Common Pitfalls & Gotchas

**1. Device PM callbacks block system sleep**  
If any device's `pm_control()` returns an error or takes too long, the system PM transition fails silently. Your device might stay awake, preventing deep sleep. Always keep device PM callbacks under 1ms, or use `k_work` to defer long operations.

**2. Runtime PM doesn't auto-suspend**  
`CONFIG_PM_DEVICE_RUNTIME=y` only enables the API — you must explicitly call `pm_device_action_run()` to suspend devices. Zephyr won't magically detect idle peripherals. I wasted two days wondering why my UART never slept.

**3. Residency time math is critical**  
The default residency for `PM_STATE_SUSPEND_TO_RAM` is often 10ms. If your idle period is 5ms, the system will never enter that state. Check `pm_state_residency_get()` and adjust via `pm_state_set_residency()` if needed.

## Try It Yourself

1. **Profile your current idle** — Add `CONFIG_PM_STATS=y` and `CONFIG_SHELL=y` to your project. Flash, run `pm stats` after 30 seconds. How many times does your system enter each state? If `PM_STATE_ACTIVE` dominates, your idle loop is too busy.

2. **Add runtime PM to a UART** — Pick a UART you only use for debug output. Wrap each `printk()` or `uart_fifo_fill()` with `pm_device_action_run(dev, PM_DEVICE_ACTION_RESUME)` before and `...SUSPEND` after. Measure current drop with a power profiler.

3. **Block deep sleep during ADC sampling** — If you sample an ADC every 100ms, the sample takes 2ms. Use `pm_state_exit_post_ops()` to block `SUSPEND_TO_RAM` during the 2ms window, then re-enable it. Compare average current with and without the constraint.

## Next Up

Tomorrow I'm tackling **Zephyr Tickless Idle & Wake-Up Sources** — how to configure the system tick to stop during deep sleep, and how to use GPIO, RTC, or comparator interrupts to wake the system without wasting power on periodic timer interrupts. We'll also look at the `pm_system_resume()` path and why your first wake-up might crash if you forget to reinitialize the system timer.
