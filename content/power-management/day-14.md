---
title: "Day 14: Zephyr Tickless Idle & Wake-Up Sources"
date: 2026-06-26
tags: ["til", "power-management", "tickless", "idle", "wakeup"]
---

## What I Explored Today

Today I dug into Zephyr’s tickless idle system and how it interacts with wake-up sources. The goal was to understand how to eliminate periodic timer interrupts during idle, letting the CPU sleep for extended periods until a real event (GPIO, RTC, UART) wakes it. I traced through the kernel idle path, configured a tickless kernel on an nRF52840 DK, and validated that the system actually stops the SysTick timer in deep sleep. The results: a drop from ~3 µA with periodic ticks to ~0.7 µA in tickless idle, with wake-up from a button GPIO.

## The Core Concept

The default Zephyr kernel uses a periodic tick timer (typically SysTick on ARM) that fires every `CONFIG_SYS_CLOCK_TICKS_PER_SEC` (e.g., 100 Hz). Even when the CPU is idle, this timer keeps waking the core every 10 ms to increment the system tick counter. In a battery-powered device, those 100 wake-ups per second dominate the sleep current.

Tickless idle eliminates this. Instead of a fixed periodic tick, the kernel programs a one-shot timer to fire at the next scheduled timeout (e.g., a delayed work or k_timer). If no timeout is pending, the timer is not programmed at all, and the CPU can enter a deep sleep state indefinitely. The wake-up source becomes the real hardware event—an external interrupt, an RTC alarm, or a UART edge.

Zephyr’s PM subsystem handles this via `pm_system_resume()` and `pm_system_suspend()`. The idle thread calls `k_cpu_idle()` or `k_cpu_atomic_idle()`, which eventually invokes the SoC-specific `sys_pm_idle_exit_notify()` and the tickless idle driver. The key config is `CONFIG_TICKLESS_KERNEL=y`, which enables the one-shot timer mode.

## Key Commands / Configuration / Code

### 1. Enable Tickless Kernel in `prj.conf`
```kconfig
# Enable tickless idle (one-shot timer mode)
CONFIG_TICKLESS_KERNEL=y

# Optional: reduce idle stack size (tickless uses less)
CONFIG_IDLE_STACK_SIZE=512

# Enable PM subsystem for deeper sleep states
CONFIG_PM=y
CONFIG_PM_DEVICE=y

# Set system clock rate (lower = less overhead)
CONFIG_SYS_CLOCK_TICKS_PER_SEC=100
```
*Note: `CONFIG_TICKLESS_KERNEL` is automatically selected on most ARM SoCs when `CONFIG_PM=y`, but explicitly setting it ensures the one-shot timer driver is compiled.*

### 2. Minimal Tickless Idle Test Application
```c
#include <zephyr/kernel.h>
#include <zephyr/pm/pm.h>
#include <zephyr/drivers/gpio.h>

/* Button for wake-up (GPIO 0.13 on nRF52840 DK) */
#define WAKEUP_PIN 13
#define WAKEUP_PORT DT_NODELABEL(gpio0)

static struct gpio_callback wakeup_cb;

void wakeup_handler(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    printk("Woke up from GPIO!\n");
}

void main(void)
{
    const struct device *gpio_dev = DEVICE_DT_GET(WAKEUP_PORT);
    gpio_pin_configure(gpio_dev, WAKEUP_PIN, GPIO_INPUT | GPIO_PULL_UP);
    gpio_pin_interrupt_configure(gpio_dev, WAKEUP_PIN, GPIO_INT_EDGE_FALLING);
    gpio_init_callback(&wakeup_cb, wakeup_handler, BIT(WAKEUP_PIN));
    gpio_add_callback(gpio_dev, &wakeup_cb);

    printk("Tickless idle demo. Press button to wake.\n");

    while (1) {
        /* Enter tickless idle - kernel will stop SysTick */
        k_sleep(K_SECONDS(10));
        printk("Woke from k_sleep!\n");
    }
}
```

### 3. Verify Tickless Behavior with Power Profiling
```bash
# Build with debug prints for PM transitions
west build -b nrf52840dk_nrf52840 -t menuconfig
# Enable: CONFIG_PM_DEBUG=y, CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=2048

# Flash and monitor with RTT
west flash
nrfjprog --rtt
```
Expected output: after `k_sleep(10)`, the device sleeps for 10 seconds with no periodic interrupts. A button press wakes it immediately.

## Common Pitfalls & Gotchas

### 1. **SysTick Still Runs on Some SoCs**
On some Cortex-M parts, the SysTick timer cannot be fully disabled in tickless mode—it may still count down but not generate interrupts. Check your SoC’s tickless driver (`drivers/timer/`). For nRF52, the `nrf_rtc_timer` driver replaces SysTick entirely. If you see ~1 µA instead of <1 µA, verify the driver is active: `CONFIG_NRF_RTC_TIMER=y`.

### 2. **Wake-Up Source Must Be Configured Before Sleep**
If you configure a GPIO interrupt after calling `k_sleep()`, the interrupt won’t be armed. Always set up wake-up sources (GPIO, RTC, etc.) *before* entering idle. Use `pm_constraint_set(PM_STATE_SOFT_OFF)` to prevent entry into states that disable the wake-up controller.

### 3. **Tickless + UART RX Can Miss Bytes**
If UART is used as a wake-up source, the RX pin must be configured for edge-triggered interrupts. In tickless idle, the UART clock may be gated. Use `uart_irq_rx_enable()` and ensure the UART device supports wake from idle (check `pm_device_wakeup_enable()`). On nRF52, the UARTE peripheral can wake from STOP mode but not from OFF mode.

## Try It Yourself

1. **Measure the current difference**: Build the same application with and without `CONFIG_TICKLESS_KERNEL=y`. Use a DMM or nRF Power Profiler to measure idle current. Expect a 3–10x reduction.

2. **Add an RTC wake-up**: Configure the nRF RTC to generate an alarm every 30 seconds. Use `k_timer` with a 30-second period and verify that the device wakes exactly at the alarm, not at a tick boundary.

3. **Debug the idle path**: Enable `CONFIG_PM_DEBUG=y` and `CONFIG_SCHED_DEBUG=y`. Add a print in `pm_system_suspend()` (in `subsys/pm/pm.c`) to see which state the kernel selects. Confirm that `PM_STATE_SOFT_OFF` is entered when no timers are pending.

## Next Up

Tomorrow: **Optimizing a Zephyr BLE Beacon for Sub-10µA Sleep** — we’ll combine tickless idle with the Bluetooth LE advertising stack, configure the nRF52840’s RADIO for periodic wake-ups, and tune the sleep current to single-digit microamps. Bring your power profiler.
