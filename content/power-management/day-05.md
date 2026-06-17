---
title: "Day 05: Wakeup Sources: Configuring & Debugging Wakeup Events"
date: 2026-06-17
tags: ["til", "power-management", "wakeup", "wakelock"]
---

## What I Explored Today

Today I dove deep into wakeup sources — the hardware and software mechanisms that bring a sleeping system back to life. I spent the morning tracing through `/sys/kernel/debug/wakeup_sources` on an i.MX8M Plus board, then moved to configuring GPIO wakeup on an STM32MP157. The key insight: a system is only as power-efficient as its wakeup architecture. If you can't reliably wake, you can't safely sleep.

## The Core Concept

Wakeup sources are the bridge between deep sleep and active operation. They must be:
- **Low-power enough** to remain armed during sleep
- **Deterministic** — no false wakes, no missed events
- **Debuggable** — you need to know *why* the system woke

The fundamental tradeoff: more wakeup sources = more power during sleep (leakage + monitoring circuitry). Fewer sources = longer sleep but risk of missing critical events.

On Linux, wakeup sources are tracked through the `struct wakeup_source` framework. Every source has:
- A name (for debugging)
- A `wakeup_count` (how many times it triggered)
- An `active_count` (currently held wakelocks)
- A `last_time` (timestamp of last event)

The kernel uses these to decide whether to abort suspend or allow it to proceed. If a wakeup event occurs *during* the suspend sequence, the kernel cancels the suspend and returns to active state.

## Key Commands / Configuration / Code

### 1. Inspecting Wakeup Sources (Runtime)

```bash
# Show all registered wakeup sources with statistics
cat /sys/kernel/debug/wakeup_sources

# Example output:
# name                    active_count  event_count  wakeup_count  expire_count  ...
# alarmtimer              0             12           12            0
# fec_enet                0             3            3             0
# gpio-keys               0             1            1             0
# 3-0048                  0             0            0             0
```

The `event_count` column is critical — it shows how many times this source triggered. If a source has a high `event_count` but you didn't intend to wake, you have a spurious wakeup.

### 2. Configuring GPIO Wakeup (Device Tree)

On the STM32MP157, I configured a GPIO button as a wakeup source:

```dts
&gpioa {
    wakeup-button {
        compatible = "gpio-keys";
        pinctrl-0 = <&wakeup_pins>;
        status = "okay";

        button-wake {
            label = "WAKEUP_BTN";
            gpios = <&gpioa 14 GPIO_ACTIVE_LOW>;
            linux,code = <KEY_WAKEUP>;
            gpio-key,wakeup;                    /* Enable wakeup capability */
            wakeup-source;                      /* Mark as wakeup source */
        };
    };
};
```

The `gpio-key,wakeup` and `wakeup-source` properties are both required — the first enables the IRQ to be configured for wake, the second registers it with the PM core.

### 3. Debugging Wakeup with ftrace

```bash
# Trace wakeup source registration and events
echo 1 > /sys/kernel/debug/tracing/events/power/wakeup_source_activate/enable
echo 1 > /sys/kernel/debug/tracing/events/power/wakeup_source_deactivate/enable
cat /sys/kernel/debug/tracing/trace_pipe

# You'll see lines like:
# <idle>-0     [000] d..3.  1234.567890: wakeup_source_activate: wakeup_source=gpio-keys state=0
# <idle>-0     [000] d..3.  1234.567895: wakeup_source_deactivate: wakeup_source=gpio-keys state=1
```

### 4. Userspace Wakelock Control (Android-style)

```c
// Example: Acquire a wakelock from userspace (requires CONFIG_PM_WAKELOCKS)
#include <fcntl.h>
#include <unistd.h>
#include <string.h>

int main() {
    int fd = open("/sys/power/wake_lock", O_WRONLY);
    if (fd < 0) {
        perror("Failed to open wake_lock");
        return -1;
    }

    // Acquire wakelock named "my_app_lock"
    write(fd, "my_app_lock", strlen("my_app_lock"));
    // ... do work ...
    // Release by writing to wake_unlock
    int fd_unlock = open("/sys/power/wake_unlock", O_WRONLY);
    write(fd_unlock, "my_app_lock", strlen("my_app_lock"));

    close(fd);
    close(fd_unlock);
    return 0;
}
```

**Warning:** Userspace wakelocks are a crutch. They prevent suspend entirely. Use them only for short, bounded operations.

## Common Pitfalls & Gotchas

### 1. The "Ghost Wake" — IRQ Storm from Floating GPIOs
If a GPIO wakeup pin is left floating or has a weak pull, noise can trigger wake events. I once spent two days debugging a board that woke every 30 seconds — turned out the wakeup GPIO had an internal pull-down that was too weak for the button's open-drain output. **Always verify the pull configuration matches your hardware.**

### 2. Wakeup Counters Reset on Reboot
The `wakeup_count` in `/sys/kernel/debug/wakeup_sources` resets to zero after every boot. If you're debugging intermittent wakeups, you need to capture the counters *before* the next suspend attempt. Use a script that logs them on each wake:

```bash
#!/bin/sh
# Log wakeup sources on every resume
while true; do
    cat /sys/kernel/debug/wakeup_sources >> /var/log/wakeup_sources.log
    echo "---" >> /var/log/wakeup_sources.log
    echo mem > /sys/power/state
done
```

### 3. The Suspend Abort Loop
If a wakeup source is *constantly* active (e.g., a button stuck pressed), the kernel will immediately abort every suspend attempt. Check `dmesg` for:
```
PM: suspend entry (deep)
PM: suspend exit
PM: Some devices failed to suspend, or early wake event detected
```
The fix: disable that wakeup source temporarily with:
```bash
echo disabled > /sys/devices/platform/soc/.../power/wakeup
```

## Try It Yourself

1. **Audit your board's wakeup sources**: Run `cat /sys/kernel/debug/wakeup_sources` and identify which sources have non-zero `event_count`. For each, determine if it's intentional or a spurious wake.

2. **Add a GPIO wakeup button**: Modify your device tree to add a `gpio-keys` node with `wakeup-source` property. Test by entering `echo mem > /sys/power/state` and pressing the button.

3. **Trace a wakeup event**: Enable the `power:wakeup_source_*` ftrace events, enter suspend, trigger a wake, then examine the trace to see the exact sequence of activation/deactivation.

## Next Up

Tomorrow we shift from sleep states to active power management: **cpufreq: Governors, Policies & DVFS on Embedded**. We'll explore how to tune frequency scaling for the sweet spot between responsiveness and battery life, and why `performance` governor is almost never the right choice for production.
