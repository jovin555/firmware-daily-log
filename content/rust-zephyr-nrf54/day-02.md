---
title: "Day 02: Zephyr on Nordic SoCs: nrfx HAL & Devicetree Overlays"
date: 2026-07-11
tags: ["til", "rust-zephyr-nrf54", "zephyr", "nrfx"]
---

## What I Explored Today

Today I dug into how Zephyr actually talks to the nRF54LM20 hardware. The two pillars are the nrfx hardware abstraction layer (Nordic's low-level peripheral driver library) and the devicetree overlay system that lets us reconfigure hardware without touching vendor code. I built a minimal blinky that toggles a GPIO using nrfx directly, then switched to a devicetree-driven approach to see how the two worlds connect.

## The Core Concept

Zephyr's hardware access model is layered, and understanding the layers matters when you're bringing up a new board or optimizing a peripheral path.

At the bottom is **nrfx** — Nordic's official C HAL. It's a register-level library that handles the bit-banging details for UART, SPI, GPIOTE, TIMER, and so on. Zephyr's own peripheral drivers (like `gpio_nrfx.c`) call into nrfx internally. But you can also call nrfx directly from application code, which is useful when you need precise control or want to bypass Zephyr's power management hooks.

Above that sits the **devicetree**. This is Zephyr's hardware description language (DTS). It defines what peripherals exist, their memory addresses, interrupt numbers, and pin assignments. The key insight: devicetree is *not* configuration — it's *metadata*. The actual driver code reads this metadata at build time via generated macros.

**Overlays** are your escape hatch. The base devicetree for the nRF54LM20DK defines the "stock" hardware. An overlay file lets you add nodes, change properties, or remap pins without editing the vendor's `.dts`. This is how you add a custom sensor, reassign UART to different pins, or enable a peripheral that's disabled by default.

The bridge between devicetree and nrfx is the `nrfx` driver instances. When you see `&uart0 { status = "okay"; }` in an overlay, Zephyr's build system generates a `DEVICE_DT_GET` macro that resolves to the nrfx UART instance (e.g., `NRF_UART0`). The nrfx API then uses that instance pointer to access the hardware registers.

## Key Commands / Configuration / Code

### Direct nrfx GPIO toggle (no devicetree)

```c
#include <nrfx_gpiote.h>

// Pin 0.13 on nRF54LM20 — check your board's silkscreen
#define LED_PIN 13

void main(void)
{
    nrfx_err_t err;

    // Initialize GPIOTE (GPIO Task/Event) peripheral
    err = nrfx_gpiote_init();
    __ASSERT(err == NRFX_SUCCESS, "GPIOTE init failed");

    // Configure pin as output, initial low
    nrfx_gpiote_out_config_t cfg = NRFX_GPIOTE_CONFIG_OUT_SIMPLE(false);
    err = nrfx_gpiote_out_init(LED_PIN, &cfg);
    __ASSERT(err == NRFX_SUCCESS, "GPIO out init failed");

    while (1) {
        nrfx_gpiote_out_toggle(LED_PIN);
        k_sleep(K_MSEC(500));
    }
}
```

### Devicetree overlay approach (preferred)

Create `boards/nrf54lm20dk_nrf54lm20.overlay`:

```dts
/ {
    leds {
        compatible = "gpio-leds";
        led0: led_0 {
            gpios = <&gpio0 13 GPIO_ACTIVE_HIGH>;
            label = "Red LED";
        };
    };
};
```

Then in your application:

```c
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

#define LED0_NODE DT_ALIAS(led0)

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

void main(void)
{
    gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);

    while (1) {
        gpio_pin_toggle_dt(&led);
        k_sleep(K_MSEC(500));
    }
}
```

Build with:

```bash
west build -b nrf54lm20dk/nrf54lm20 -p always
```

The overlay is automatically picked up if placed in the correct board directory. For custom overlays, use `-DEXTRA_DTC_OVERLAY_FILE=my_overlay.overlay`.

## Common Pitfalls & Gotchas

**1. Pin numbers are not GPIO port + pin.**
The nRF54LM20 uses a single GPIO port (port 0) with up to 22 pins. But the devicetree node `&gpio0` expects a two-cell specifier: `<&gpio0 13 0>`. The second cell is flags (active high/low, pull-up, etc.). If you write `<&gpio0 13>` without the flags cell, the build will fail with a cryptic "bad cell count" error. Always use the `GPIO_DT_SPEC_GET` macro — it handles the cell count correctly.

**2. nrfx direct calls bypass Zephyr's power management.**
If you call `nrfx_gpiote_out_init()` directly, Zephyr's PM subsystem doesn't know the pin is in use. This can cause the pin to lose state during sleep transitions. For production code, prefer the Zephyr GPIO driver unless you have a specific latency or register-access requirement.

**3. Overlay files are case-sensitive and path-dependent.**
The build system looks for overlays in `boards/<board_name>.overlay` relative to your project root. If you name the file `nRF54LM20DK.overlay` (capital R), it won't match. Use `nrf54lm20dk_nrf54lm20.overlay` exactly. Run `west build -t guiconfig` to verify your overlay was parsed.

## Try It Yourself

1. **Remap the LED to a different pin.** Change the overlay to use GPIO 0.14 instead of 0.13. Rebuild and verify the LED toggles on the new pin. This confirms you understand the devicetree → pin mapping.

2. **Add a second LED via overlay.** Create a `led1` node using a different pin. In your C code, use `DT_ALIAS(led1)` to get the second spec and toggle both LEDs alternately. This exercises multi-node devicetree access.

3. **Call nrfx directly alongside Zephyr driver.** Initialize one LED with `gpio_pin_configure_dt()` and another with `nrfx_gpiote_out_init()`. Observe that both work, but note the difference in initialization order and error handling.

## Next Up

Tomorrow we bridge Rust and Zephyr. I'll set up the `zephyr-rust` crate, configure the Rust toolchain for the nRF54LM20 target, and write our first Rust application that blinks an LED using the Zephyr GPIO API from Rust. We'll cover the linker script adjustments and the `cargo build` integration that makes it all work.
