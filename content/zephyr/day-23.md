---
title: "Day 23: Optimizing for Ultra-Low Power: Tickless Idle"
date: 2026-07-05
tags: ["til", "zephyr", "low-power", "optimization"]
---

## What I Explored Today

Today I dug into Zephyr's tickless idle system — the mechanism that lets the kernel stop the system timer tick when the CPU enters idle, dramatically reducing power consumption in battery-powered devices. I've been chasing microamps in a BLE sensor node, and understanding how tickless idle interacts with the scheduler, the timer driver, and SoC sleep states was the missing piece. The default periodic tick mode keeps the CPU waking up every millisecond or so just to service a timer interrupt — that's death for ultra-low-power designs. Tickless idle eliminates that overhead.

## The Core Concept

The traditional RTOS tick is a periodic timer interrupt that fires at a fixed rate (typically 100–1000 Hz) to let the kernel manage timeouts, thread sleeps, and preemption. In a battery-powered system that spends 99% of its time sleeping, that periodic tick is pure waste. Every tick wakes the CPU from a deep sleep state, burns through leakage current, and shortens battery life.

Tickless idle solves this by reprogramming the hardware timer to fire at the *next* scheduled timeout, rather than at a fixed interval. When the idle thread runs and there are no threads ready, the kernel calculates the earliest future timeout (from `k_sleep()`, `k_timer`, or `k_queue_get()` with a timeout), sets the timer to that absolute time, and then puts the CPU into its deepest available sleep state. The timer interrupt fires exactly when needed, the kernel handles the timeout, and the system resumes normally. No wasted ticks.

The key insight: this isn't just about the idle thread. The entire kernel's timeout management must be event-driven rather than polled. Zephyr's scheduler uses a sorted linked list of timeouts, and the tickless idle code simply reads the head of that list to know when to wake.

## Key Commands / Configuration / Code

### Enabling Tickless Idle

In your board's `Kconfig` or `prj.conf`:

```kconfig
# Enable tickless idle (default on most modern SoCs)
CONFIG_TICKLESS_IDLE=y

# Optional: set minimum sleep duration to avoid shallow sleeps
CONFIG_TICKLESS_IDLE_MIN_TICKS=2

# Optional: enable kernel idle hooks for custom sleep states
CONFIG_PM=y
CONFIG_PM_DEVICE=y
```

### Checking if Tickless is Active

At runtime, verify with `CONFIG_TICKLESS_IDLE` and inspect the timer driver:

```c
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

void check_tickless(void)
{
    if (IS_ENABLED(CONFIG_TICKLESS_IDLE)) {
        printk("Tickless idle is enabled\n");
    } else {
        printk("Using periodic ticks\n");
    }
}
```

### Custom Idle Hook (SoC-specific)

For deeper sleep states, implement a custom idle function in your board's `soc.c` or via `pm_idle_exit_notification`:

```c
#include <zephyr/pm/pm.h>
#include <zephyr/pm/device.h>

/* Called by the idle thread before entering sleep */
void pm_state_set(enum pm_state state, uint8_t substate_id)
{
    /* Example: enter STANDBY mode on STM32 */
    if (state == PM_STATE_STANDBY) {
        /* Disable peripherals, set wakeup sources */
        pm_device_action_all(PM_DEVICE_ACTION_SUSPEND);
        /* Enter deep sleep — returns after wakeup */
        HAL_PWR_EnterSTANDBYMode();
    }
}

/* Called after wakeup to restore state */
void pm_state_exit_notification(enum pm_state state, uint8_t substate_id)
{
    if (state == PM_STATE_STANDBY) {
        /* Re-enable peripherals, restore clocks */
        pm_device_action_all(PM_DEVICE_ACTION_RESUME);
        /* System clock must be reconfigured */
        SystemClock_Config();
    }
}
```

### Measuring the Effect

Use a logic analyzer or oscilloscope on a GPIO toggled in the idle entry/exit:

```c
#include <zephyr/drivers/gpio.h>

static const struct gpio_dt_spec idle_pin = GPIO_DT_SPEC_GET(DT_NODELABEL(idle_gpio), gpios);

void idle_entry(void)
{
    gpio_pin_toggle_dt(&idle_pin);
}

void idle_exit(void)
{
    gpio_pin_toggle_dt(&idle_pin);
}

/* Register hooks — called from idle thread */
K_IDLE_ENTRY_FUNC(idle_entry);
K_IDLE_EXIT_FUNC(idle_exit);
```

## Common Pitfalls & Gotchas

**1. Timer driver must support tickless mode.** Not all SoC timer peripherals can reprogram the compare value on the fly. If your timer driver doesn't implement `sys_clock_set_timeout()`, the kernel falls back to periodic ticks. Check `drivers/timer/` for your SoC — if it's missing, you'll need to write the driver support.

**2. Deep sleep states break debugger connectivity.** When the CPU enters STOP or STANDBY mode, the debug interface (SWD/JTAG) often loses connection. You'll need to add a debug-mode check (`LL_DBGMCU_EnableDBGSleepMode()` on STM32) or use a GPIO wakeup to keep the debugger alive during development.

**3. Tickless idle + `k_busy_wait()` = disaster.** `k_busy_wait()` is a spin-loop that expects the tick to keep running. If you call it while tickless idle is active, the system won't wake until the next timeout, and your busy-wait will overshoot by orders of magnitude. Always use `k_sleep()` or hardware timers for delays > a few microseconds.

## Try It Yourself

1. **Enable tickless idle on your board** — add `CONFIG_TICKLESS_IDLE=y` to `prj.conf`, build, and measure idle current with a multimeter. Compare to the periodic tick baseline (disable tickless idle).

2. **Add a GPIO toggle in the idle entry/exit hooks** — use `K_IDLE_ENTRY_FUNC` and `K_IDLE_EXIT_FUNC` to capture the idle pattern on a scope. Verify that the time between wakeups matches your longest timeout, not a fixed 1 ms tick.

3. **Implement a custom deep sleep state** — for an STM32 or nRF5x board, write a `pm_state_set()` handler that enters STOP2 or OFF mode. Ensure all peripherals are suspended and the wakeup source (e.g., RTC alarm or GPIO interrupt) is configured.

## Next Up

Tomorrow we'll tackle the **Logging Subsystem: LOG_MODULE_REGISTER** — how to set up structured, filterable logging that doesn't bloat your binary or kill your real-time performance. We'll cover compile-time filtering, runtime backends, and the dreaded log string duplication trap.

---
