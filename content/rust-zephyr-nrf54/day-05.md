---
title: "Day 05: Devicetree Bindings in Rust: Accessing Zephyr DT Nodes"
date: 2026-07-14
tags: ["til", "rust-zephyr-nrf54", "devicetree", "rust"]
---

## What I Explored Today

Today I bridged the gap between Zephyr's hardware description language (devicetree) and Rust's type system. I learned how to access devicetree nodes, read their properties, and map peripheral instances to Rust code using the `zephyr-sys` bindings and the `devicetree` module. The key insight: Zephyr's C macros like `DT_NODELABEL` and `DT_PROP` have Rust equivalents that feel more natural once you understand the macro expansion pipeline.

## The Core Concept

Devicetree (DT) is Zephyr's way of describing hardware that doesn't change at runtime—pin mappings, peripheral base addresses, clock configurations. In C, you'd write `#define MY_LED DT_ALIAS(led0)` and then use `gpio_pin_configure(DEVICE_DT_GET(MY_LED), ...)`. In Rust, we don't have the C preprocessor, but we have `zephyr::devicetree::*` modules that generate Rust constants at compile time from the same `.dts` files.

The "why" matters: DT bindings let you write hardware-agnostic driver code. Your Rust application can reference `led0` without knowing if it's on GPIO0 pin 13 or GPIO1 pin 4. The board's `.dts` file provides that mapping. This is critical for code reuse across the nRF54LM20's many possible pin configurations.

## Key Commands / Configuration / Code

First, verify your devicetree is being parsed correctly. The nRF54LM20 DK's default `.dts` includes a `leds` node. Let's inspect it:

```bash
# From your Zephyr build directory
west build -t guiconfig  # Check DT overlay is applied
cat build/zephyr/zephyr.dts | grep -A 10 "leds"
```

Expected output fragment:
```
leds {
    compatible = "gpio-leds";
    led0: led_0 {
        gpios = <&gpio0 13 GPIO_ACTIVE_LOW>;
        label = "Green LED 0";
    };
};
```

Now, in your Rust application (`src/main.rs`):

```rust
//! Accessing devicetree nodes in Rust with zephyr-sys
//! Requires: CONFIG_DEVICE=y in prj.conf

use zephyr::devicetree::*;

// The DT_NODELABEL macro becomes a Rust constant
// led0 is defined in the board's .dts as a node label
const LED0_NODE: DTNodeLabel<{ c"led0" }> = DTNodeLabel::new();

// Read properties at compile time
// DT_PROP_OR(node, label, default) -> &str
const LED0_LABEL: &str = DTPropOr!(LED0_NODE, label, "unknown");

// For GPIO specifiers, we need the gpio_dt_spec structure
// This is the Rust equivalent of DEVICE_DT_GET + gpio_dt_spec
use zephyr::gpio::GpioDtSpec;

// Create a GPIO spec from the devicetree node
// This resolves the gpios property into (port, pin, flags)
let led_spec = GpioDtSpec::from_node::<{ c"led0" }>();

// At runtime, configure the pin
// led_spec.port is a &Device, led_spec.pin is u16, led_spec.flags is gpio_flags_t
let ret = unsafe {
    gpio_pin_configure(
        led_spec.port.as_ptr(),
        led_spec.pin,
        led_spec.flags as u32,
    )
};
if ret < 0 {
    // Handle error - typically -EINVAL if node not found
    panic!("Failed to configure LED pin: {}", ret);
}
```

The `DTNodeLabel` type uses const generics with C-string literals (`c"..."`). This is a Rust nightly feature (enabled in your `rust-toolchain.toml`). The `DTPropOr!` macro expands to a `&str` constant—no runtime string parsing.

For more complex properties like `reg` or `interrupts`:

```rust
// Reading a u32 property with DT_PROP
// Assume a node with: my-sensor@0 { reg = <0x4000 0x100>; };
const SENSOR_BASE: u32 = DTRegAddr!(DT_NODELABEL!(my_sensor));
const SENSOR_SIZE: u32 = DTRegSize!(DT_NODELABEL!(my_sensor));

// Or for a single-cell property like clock-frequency
const CLOCK_FREQ: u32 = DTProp!(DT_NODELABEL!(clk_32k), clock_frequency);
```

## Common Pitfalls & Gotchas

1. **Missing `CONFIG_DEVICE` in prj.conf**: If you get linker errors about `__device_dts_ord_*` symbols, you forgot to enable device support. Add `CONFIG_DEVICE=y` and `CONFIG_GPIO=y` to your `prj.conf`. The Rust bindings generate references to device structs that don't exist without these Kconfig options.

2. **Node label vs. alias confusion**: `DT_NODELABEL!(led0)` works only if `led0:` appears in the `.dts`. For aliases (like `aliases { led0 = &led0; }`), use `DT_ALIAS!(led0)` which returns a node identifier. Mixing them up gives compile-time errors like "node not found in devicetree".

3. **GPIO flags endianness**: The `gpios` property stores flags in the third cell. On nRF54, `GPIO_ACTIVE_LOW` is `1`. But `GpioDtSpec::from_node()` reads the raw cell value. If your LED is active low, you must invert the logic yourself—the spec doesn't automatically apply the flag. Always check `led_spec.flags & GPIO_ACTIVE_LOW` before setting the pin.

## Try It Yourself

1. **Read all LED labels**: Write a Rust function that iterates over `DT_INST_FOREACH_STATUS_OKAY(gpio_leds)` and prints each LED's label property. Use `DT_PROP_OR` to handle missing labels gracefully.

2. **Validate a pin mapping**: Add a compile-time assertion that `led0` uses GPIO0 pin 13 (the nRF54LM20 DK default). Use `DT_PROP(DT_NODELABEL!(led0), gpios)` and `DT_GPIO_PIN` to extract the pin number, then `static_assert!` it equals 13.

3. **Map a UART peripheral**: Find the `uart0` node in your `.dts`, read its `current-speed` property, and print it at boot. Use `DT_PROP(DT_NODELABEL!(uart0), current_speed)` (note: underscore, not hyphen—devicetree properties with hyphens become underscores in Rust).

## Next Up

Tomorrow we make that LED blink. We'll dive into Zephyr's GPIO API from Rust—configuring pins as outputs, toggling them with `gpio_pin_set`, and handling the `struct device` pointer correctly. You'll see how the devicetree bindings from today connect to real hardware control. Get ready to see that green LED flash.
