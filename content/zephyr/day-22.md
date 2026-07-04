---
title: "Day 22: Power Management: PM States & Hooks"
date: 2026-07-04
tags: ["til", "zephyr", "power", "pm"]
---

## What I Explored Today

Today I dove into Zephyr's power management subsystem, specifically the PM state machine and the hooks that let us control transitions between states. After spending weeks building a battery-powered sensor node, I realized that simply entering idle wasn't enough—I needed fine-grained control over which subsystems powered down and when. Zephyr's PM framework provides exactly that: a structured way to define power states, register transition callbacks, and hook into the scheduler's idle path.

## The Core Concept

Zephyr's power management isn't just about putting the CPU to sleep—it's about defining a hierarchy of power states that map to your hardware's capabilities. The PM subsystem defines three primary states: PM_STATE_ACTIVE (normal operation), PM_STATE_SUSPEND_TO_IDLE (light sleep, CPU halted, RAM retained), and PM_STATE_SUSPEND_TO_RAM (deep sleep, most peripherals off, RAM in self-refresh). You can also define custom states via Kconfig.

The real power comes from **hooks**—callback functions that the kernel calls at specific points during state transitions. These hooks let you:
- Save/restore peripheral state (registers, DMA descriptors)
- Gate clocks and power rails
- Notify external PMICs or voltage regulators
- Log transition timing for profiling

The hooks run in a specific order: `pm_notifier_register()` lets you attach a callback that fires *before* entering a state (PM_PRE_STATE_CHANGE) and *after* resuming (PM_POST_STATE_CHANGE). This is critical: you must save state in the pre-hook and restore in the post-hook, because the CPU may lose register contents in deep sleep.

## Key Commands / Configuration / Code

**Enable PM in your project's prj.conf:**
```kconfig
# Enable power management framework
CONFIG_PM=y
# Enable device power management (per-device PM)
CONFIG_DEVICE_POWER_MANAGEMENT=y
# Optional: enable PM stats for debugging
CONFIG_PM_STATS=y
```

**Register a PM notifier hook:**
```c
#include <zephyr/pm/pm.h>
#include <zephyr/pm/state.h>

/* User data passed to callback */
struct my_pm_data {
    uint32_t saved_clock_config;
    bool uart_suspended;
};

/* The callback function */
static int my_pm_notifier(const struct pm_notification *notif, void *user_data)
{
    struct my_pm_data *data = (struct my_pm_data *)user_data;

    switch (notif->type) {
    case PM_PRE_STATE_CHANGE:
        /* Save critical state before sleeping */
        if (notif->state == PM_STATE_SUSPEND_TO_RAM) {
            /* Save clock configuration */
            data->saved_clock_config = NRF_CLOCK->HFCLKSTAT;
            /* Gate UART clock */
            pm_device_action_run(DEVICE_DT_GET(DT_NODELABEL(uart0)),
                                 PM_DEVICE_ACTION_SUSPEND);
            data->uart_suspended = true;
        }
        break;
    case PM_POST_STATE_CHANGE:
        /* Restore state after wake */
        if (data->uart_suspended) {
            pm_device_action_run(DEVICE_DT_GET(DT_NODELABEL(uart0)),
                                 PM_DEVICE_ACTION_RESUME);
            data->uart_suspended = false;
        }
        break;
    }
    return 0;
}

/* Register the notifier in your main() or init function */
void main(void)
{
    static struct my_pm_data pm_data = {0};
    static struct pm_notifier notifier = {
        .callback = my_pm_notifier,
        .user_data = &pm_data
    };

    pm_notifier_register(&notifier);
    /* ... rest of app ... */
}
```

**Trigger a state transition manually (for testing):**
```c
/* Force entry into SUSPEND_TO_RAM */
int ret = pm_state_force(0, &(struct pm_state_info){
    .state = PM_STATE_SUSPEND_TO_RAM,
    .substate_id = 0,
});
if (ret < 0) {
    printk("Failed to enter PM state: %d\n", ret);
}
```

**Check current PM state:**
```c
enum pm_state current_state = pm_state_get();
printk("Current PM state: %d\n", current_state);
```

## Common Pitfalls & Gotchas

1. **Not saving volatile peripheral state in the pre-hook.** If your UART has pending TX data or your SPI controller has a half-completed transaction, entering deep sleep will lose it. Always flush or save state in `PM_PRE_STATE_CHANGE`. I learned this the hard way when my sensor node woke up with a garbled UART buffer.

2. **Assuming all devices support PM.** Not every driver implements `pm_device_action_run()`. Check your driver's documentation or source—if it returns `-ENOSYS`, the device doesn't support PM and will remain powered. Use `pm_device_is_power_manageable()` to check at runtime.

3. **Forgetting to handle wake-up sources.** Entering a sleep state without configuring a wake-up source (RTC alarm, GPIO interrupt, etc.) means the system never wakes. Zephyr's PM framework doesn't automatically configure wake pins—you must do it in your board's pinmux or in the pre-hook. On nRF52, for example, you need to enable the GPIOTE event and set the SENSE bit on the waking GPIO.

4. **Stack overflow in PM hooks.** The PM hooks run in interrupt context (specifically, the idle thread's context). Keep your callbacks short and avoid blocking calls. If you need to do heavy lifting (like writing to flash), defer it to a workqueue.

## Try It Yourself

1. **Add a PM notifier to your existing project.** Register a callback that prints the current PM state every time the system transitions. Use `pm_state_get()` inside the callback to log the state name. Build and run—you'll see the idle loop entering and exiting light sleep.

2. **Force a deep sleep transition.** On a development board with a button, configure a GPIO as a wake-up source. Then call `pm_state_force()` to enter `PM_STATE_SUSPEND_TO_RAM`. Verify that pressing the button wakes the system and that your post-hook restores peripheral state correctly.

3. **Profile PM transition latency.** Enable `CONFIG_PM_STATS=y` and use `pm_stats_get()` to retrieve transition counts and durations. Add a small buffer in your notifier to log timestamps (using `k_cycle_get_32()`) before and after the transition. Compare the overhead of light sleep vs. deep sleep.

## Next Up

Tomorrow, we'll tackle **Optimizing for Ultra-Low Power: Tickless Idle**—how to eliminate the periodic timer tick so the CPU can stay in deep sleep for seconds or minutes, and how to use the RTC as a one-shot wake timer. We'll also cover the `CONFIG_TICKLESS_KERNEL` option and its interaction with PM states.
