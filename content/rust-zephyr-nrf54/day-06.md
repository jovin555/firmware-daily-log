---
title: "Day 06: GPIO & LED Control in Rust on Zephyr"
date: 2026-07-15
tags: ["til", "rust-zephyr-nrf54", "gpio", "zephyr"]
---

## What I Explored Today

Today I wired up the onboard LED on the nRF54LM20 DK using Zephyr's GPIO API from Rust. After days of build system and threading fundamentals, it was time to make something blink. I used the `zephyr::gpio` module to configure a pin as output, drive it high and low, and integrated it with a simple delay loop. The result: a blinking LED at 1 Hz, verified with a logic analyzer on P0.13 (the DK's green LED).

## The Core Concept

GPIO (General-Purpose Input/Output) is the simplest peripheral—a pin you can read or write as a digital signal. But "simple" is deceptive. The nRF54LM20 has up to 48 GPIOs, each with configurable drive strength, pull-up/down resistors, interrupt capability, and output type (push-pull vs. open-drain). In Zephyr, GPIO is abstracted through the Device Tree, which maps logical names (like `led0`) to physical pins and port controllers.

Why not just write to a raw memory-mapped register? Because Zephyr's GPIO driver handles pin multiplexing, clock gating, and power management transparently. On the nRF54, GPIOs are part of the GPIOTE peripheral, which also supports task/event triggering for low-power operation. Using the API ensures your code works across board revisions and even different SoCs.

In Rust, the `zephyr::gpio::GpioPin` type wraps the C `struct gpio_dt_spec` and provides safe methods. The key insight: you must first get a pin specification from the device tree, then configure it, then use it. The Rust bindings enforce this sequence at compile time—you can't write to an unconfigured pin.

## Key Commands / Configuration / Code

First, verify your board's device tree has the LED alias. For the nRF54LM20 DK, the relevant snippet in `nrf54lm20dk_nrf54lm20.dts`:

```dts
/ {
    leds {
        compatible = "gpio-leds";
        led0: led_0 {
            gpios = <&gpio0 13 GPIO_ACTIVE_LOW>;
            label = "Green LED";
        };
    };
    aliases {
        led0 = &led0;
    };
};
```

Note `GPIO_ACTIVE_LOW`—the LED turns on when the pin is low. This is common for LEDs connected to VDD via a resistor.

Now the Rust code. Add this to `src/main.rs`:

```rust
use zephyr::gpio::{GpioPin, OutputFlags};
use zephyr::time::Duration;
use zephyr::sys::k_sleep;

fn main() -> Result<(), zephyr::ZephyrError> {
    // Get the LED pin spec from the device tree
    // This uses the DT_ALIAS macro under the hood
    let led = GpioPin::from_devicetree("led0")?;

    // Configure as output, push-pull, initially high (LED off)
    led.configure_output(OutputFlags::OUTPUT_ACTIVE_HIGH)?;

    loop {
        // Toggle the pin state
        led.toggle()?;
        // Sleep for 500 ms
        unsafe { k_sleep(&Duration::from_millis(500).into_raw()) };
    }
}
```

Build and flash:

```bash
west build -b nrf54lm20dk/nrf54lm20/cpuapp -p always
west flash
```

The LED should blink at 1 Hz (500 ms on, 500 ms off). Because the pin is active-low, `toggle()` inverts the state: from high (off) to low (on).

For more control, use `set_low()` and `set_high()` directly:

```rust
led.set_low()?;  // LED on (active low)
led.set_high()?; // LED off
```

If you need to read a button, configure as input:

```rust
let button = GpioPin::from_devicetree("sw0")?;
button.configure_input(InputFlags::INPUT_PULL_UP)?;
let state = button.read()?; // true if high (button not pressed)
```

## Common Pitfalls & Gotchas

1. **Active polarity mismatch** — The biggest trap. If your LED is `GPIO_ACTIVE_LOW` but you call `set_high()` thinking it turns the LED on, you'll get the opposite behavior. Always check the device tree. Use `toggle()` for polarity-agnostic blinking.

2. **Missing `CONFIG_GPIO` in prj.conf** — Zephyr's GPIO driver is not enabled by default. Add this to your `prj.conf`:
   ```
   CONFIG_GPIO=y
   ```
   Without it, `GpioPin::from_devicetree()` will return an error at runtime.

3. **Port and pin number confusion** — The nRF54LM20 has multiple GPIO ports (gpio0, gpio1, etc.). The device tree alias `led0` maps to `<&gpio0 13>`, meaning port 0, pin 13. If you try to use a raw pin number without the port, you'll configure the wrong pin. Always use device tree aliases.

4. **k_sleep is unsafe** — In Zephyr's Rust bindings, `k_sleep` is currently `unsafe` because it can be called from interrupt context (where sleeping is illegal). In a main thread it's safe, but the compiler doesn't know that. Wrap it in an `unsafe` block or use the safe `zephyr::time::sleep()` helper if available in your SDK version.

## Try It Yourself

1. **Blink two LEDs alternately** — Add a second LED alias (e.g., `led1` on P0.14) and blink them in opposite phases. Use `set_high()` and `set_low()` explicitly.

2. **Button-controlled LED** — Configure a button pin as input with pull-up. Read it in a loop and turn the LED on only while the button is pressed. Add a 50 ms debounce delay.

3. **PWM-like brightness** — Without using the PWM peripheral, implement software PWM: toggle the LED rapidly with varying duty cycles (e.g., 10% on, 90% off for dim). Use `k_busy_wait()` for microsecond delays.

## Next Up

Tomorrow: **UART Communication: Async Rust Zephyr Drivers**. We'll connect the nRF54LM20 to a serial terminal, send "Hello, World!" over UART, and explore Zephyr's asynchronous UART API from Rust—including buffer management and callback handling.
