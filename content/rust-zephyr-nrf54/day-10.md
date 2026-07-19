---
title: "Day 10: Interrupt Handling: Rust ISRs in a Zephyr Context"
date: 2026-07-19
tags: ["til", "rust-zephyr-nrf54", "interrupts", "isr"]
---

## What I Explored Today

Today I wired up a real interrupt service routine (ISR) on the nRF54LM20 using Rust, bridging Zephyr's interrupt controller API with safe Rust abstractions. I focused on the GPIO pin interrupt — triggering on a button press — and handled it without `unsafe` leaking into application code. The goal was to understand how Zephyr's `IRQ_CONNECT` and `ISR_DIRECT_DECLARE` macros interact with Rust's calling conventions, and how to build a minimal, safe interrupt framework that doesn't fight the RTOS.

## The Core Concept

Interrupts are the backbone of real-time embedded systems. In Zephyr, every interrupt is registered with the kernel's interrupt controller (for nRF54LM20, that's the Nested Vectored Interrupt Controller, NVIC). The kernel manages priority, nesting, and context save/restore. Your ISR is just a C function pointer — but when you're writing it in Rust, you need to ensure the function uses the correct ABI (C calling convention) and that the Rust compiler doesn't optimize away volatile accesses or reorder memory operations.

The key insight: Zephyr's interrupt model is *static* — you define ISRs at build time via `IRQ_CONNECT` or device tree interrupts. Rust's role is to provide the handler body, manage shared state safely (using `core::sync::atomic` or a `Mutex`-like primitive), and ensure the handler is `#[no_mangle]` with `extern "C"` linkage. The nRF54LM20's NVIC supports up to 48 interrupts, with configurable priority levels (0-3, where 0 is highest). For GPIO interrupts, you configure the pin edge sensitivity in the GPIOTE peripheral, then connect the interrupt line to the NVIC.

## Key Commands / Configuration / Code

First, the device tree overlay to enable a button interrupt on P0.13 (the nRF54LM20 DK's Button 1):

```dts
// boards/nrf54lm20_dk.overlay
/ {
    buttons {
        compatible = "gpio-keys";
        button0: button_0 {
            gpios = <&gpio0 13 (GPIO_PULL_UP | GPIO_ACTIVE_LOW)>;
            label = "Button 1";
        };
    };
};
```

Now the Rust ISR. I use a static atomic flag to signal the main loop, avoiding any blocking or heap allocation inside the ISR:

```rust
// src/interrupts.rs
use core::sync::atomic::{AtomicBool, Ordering};

// Shared state between ISR and main context
static BUTTON_PRESSED: AtomicBool = AtomicBool::new(false);

// The ISR must be extern "C" and #[no_mangle] so Zephyr can find it
#[no_mangle]
pub extern "C" fn gpio_button_isr() {
    // Clear the GPIO interrupt flag (GPIOTE event)
    // This is hardware-specific: read and clear the EVENT_IN register
    // For nRF54LM20, we use the GPIOTE peripheral base address
    const GPIOTE_BASE: u32 = 0x4002_8000;
    const EVENT_IN_OFFSET: u32 = 0x100; // offset for channel 0
    const INTENCLR_OFFSET: u32 = 0x300;

    unsafe {
        // Clear the event by writing 0 to the EVENT register
        core::ptr::write_volatile(
            (GPIOTE_BASE + EVENT_IN_OFFSET) as *mut u32,
            0,
        );
        // Disable the interrupt in GPIOTE (re-enabled by main loop)
        core::ptr::write_volatile(
            (GPIOTE_BASE + INTENCLR_OFFSET) as *mut u32,
            1 << 0, // channel 0
        );
    }

    // Signal the main loop
    BUTTON_PRESSED.store(true, Ordering::Release);
}

// Safe wrapper for the main loop to check
pub fn was_button_pressed() -> bool {
    BUTTON_PRESSED.swap(false, Ordering::Acquire)
}
```

In `main.rs`, connect the ISR to the NVIC and configure the GPIO pin:

```rust
// src/main.rs
mod interrupts;

use zephyr_sys::{
    IRQ_CONNECT, // macro, not function
    irq_enable,
    device_get_binding,
    gpio_pin_configure,
    gpio_pin_interrupt_configure,
    GPIO_INT_EDGE_TO_ACTIVE,
    GPIO_OUTPUT_INACTIVE,
};

fn main() {
    // Get the GPIO device from device tree
    let dev = unsafe { device_get_binding("gpio0\0".as_ptr() as *const i8) };
    assert!(!dev.is_null(), "GPIO0 not found");

    // Configure pin 13 as input with pull-up
    let ret = unsafe {
        gpio_pin_configure(dev, 13, GPIO_OUTPUT_INACTIVE | GPIO_PULL_UP)
    };
    assert_eq!(ret, 0, "GPIO config failed");

    // Connect the ISR to IRQ line 20 (GPIOTE IRQ0 on nRF54LM20)
    // Priority 1 (0=highest, 3=lowest)
    unsafe {
        IRQ_CONNECT(20, 1, gpio_button_isr as *const (), 0);
        irq_enable(20);
    }

    // Enable edge-triggered interrupt on falling edge (button press)
    let ret = unsafe {
        gpio_pin_interrupt_configure(dev, 13, GPIO_INT_EDGE_TO_ACTIVE)
    };
    assert_eq!(ret, 0, "Interrupt config failed");

    loop {
        if interrupts::was_button_pressed() {
            // Re-enable the GPIOTE interrupt (cleared in ISR)
            unsafe {
                const INTENSET_OFFSET: u32 = 0x304;
                core::ptr::write_volatile(
                    (0x4002_8000 + INTENSET_OFFSET) as *mut u32,
                    1 << 0,
                );
            }
            k_sem_give(&my_sem); // or just print
        }
        // Sleep to save power
        k_sleep(K_MSEC(10));
    }
}
```

Build and flash:

```bash
west build -b nrf54lm20_dk/nrf54lm20/cpuapp -p always .
west flash
```

## Common Pitfalls & Gotchas

1. **Missing `extern "C"` on ISR** — If you forget `extern "C"`, the Rust compiler uses its own ABI (which may differ from C's on ARM). Zephyr's `IRQ_CONNECT` macro expects a C function pointer. The symptom is a hard fault on interrupt entry. Always annotate ISRs with `extern "C"` and `#[no_mangle]`.

2. **Forgetting to clear the interrupt flag** — The nRF54LM20's GPIOTE peripheral requires you to clear the `EVENT_IN` register by writing 0 to it. If you skip this, the interrupt fires repeatedly in an infinite loop. Zephyr's `gpio_pin_interrupt_configure` doesn't do this for you — it only enables the NVIC line. You must clear the peripheral-level event in your ISR.

3. **Re-enabling interrupts in the wrong order** — If you re-enable the GPIOTE interrupt *before* clearing the event, you get a spurious re-entry. Always clear the event first, then re-enable the interrupt in the main loop (or use a deferred handler). On nRF54LM20, the NVIC edge-triggered interrupt is level-sensitive at the peripheral — a stale event bit means the NVIC sees a constant high level.

## Try It Yourself

1. **Add a second button interrupt** — Configure P0.14 as another button with a different ISR. Use a separate atomic flag and print which button was pressed. Verify both work without interference.

2. **Measure ISR latency** — Use a GPIO toggle at the start and end of your ISR, and capture it with a logic analyzer or oscilloscope. Compare the latency when the main loop is busy (e.g., spinning on a calculation) vs. sleeping.

3. **Implement a debounce filter** — In the ISR, use a hardware timer (e.g., nRF54LM20's RTC) to schedule a deferred work item 50ms after the first edge. Only signal the main loop if the button is still pressed after the debounce period. Use Zephyr's `k_work_schedule` from a work queue.

## Next Up

Tomorrow, I'll dive into **Power Management: nRF54LM20 Low Power Modes with Zephyr PM** — configuring the system to enter `PM_STATE_SUSPEND_TO_IDLE` on idle, waking from a GPIO interrupt, and measuring current draw with the nRF54L20 DK's on-board current sensor.
