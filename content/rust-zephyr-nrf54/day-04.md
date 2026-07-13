---
title: "Day 04: Building & Flashing a Rust Zephyr App for nRF54LM20"
date: 2026-07-13
tags: ["til", "rust-zephyr-nrf54", "build", "flash"]
---

## What I Explored Today

Today I closed the loop on the toolchain setup from Day 2 and the Rust + Zephyr integration from Day 3. I built a real Rust application for the nRF54LM20, flashed it to the board, and verified it ran. The goal was simple: get a Rust binary executing on the nRF54LM20's Cortex-M33 core, with Zephyr handling the hardware initialization and runtime. After fighting with linker scripts, target triples, and flash tools, I have a repeatable build-and-flash workflow.

## The Core Concept

Building a Rust application for Zephyr on nRF54LM20 isn't like compiling a standard `cargo build` for a Linux target. Zephyr is a full RTOS with its own build system (CMake + west), and Rust needs to integrate into that pipeline. The key insight: you don't compile Rust in isolation and then link it in. Instead, you let Zephyr's build system drive the process, using CMake to invoke `rustc` with the correct target triple, linker script, and preprocessor defines that Zephyr generates.

The nRF54LM20 has a Cortex-M33 core (ARMv8-M with TrustZone), so the target triple is `thumbv8m.main-none-eabihf`. But Zephyr doesn't use the standard Rust target—it uses a custom target specification file (`thumbv8m.main-zephyr-eabi.json`) that sets the correct linker, CPU features, and ABI flags. Without this, your Rust code won't link against Zephyr's C libraries or use the correct hardware abstractions.

Flashing is equally specific. The nRF54LM20 uses a custom boot flow: you need to flash both the application image and the bootloader/SoftDevice partition. The `nrfjprog` tool from Nordic handles this, but you must specify the correct memory regions and family (`--family NRF54`).

## Key Commands / Configuration / Code

### 1. Project Structure

```
my-rust-zephyr-app/
├── CMakeLists.txt          # Zephyr CMake entry
├── prj.conf                # Zephyr Kconfig
├── src/
│   ├── main.rs             # Rust entry point
│   └── lib.rs              # Zephyr Rust bindings
├── boards/
│   └── nrf54lm20dk.overlay # Devicetree overlay (optional)
└── rust-toolchain.toml     # Pin Rust toolchain
```

### 2. CMakeLists.txt — The Glue

```cmake
# CMakeLists.txt
cmake_minimum_required(VERSION 3.20)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(my_rust_app)

# Tell Zephyr we have Rust source files
zephyr_rust_library(
    NAME rust_app
    SOURCES src/main.rs src/lib.rs
    TARGET thumbv8m.main-zephyr-eabi
    # Use Zephyr's custom target spec
    TARGET_SPEC_FILE ${ZEPHYR_BASE}/arch/arm/rust/thumbv8m.main-zephyr-eabi.json
)
```

### 3. Rust Entry Point (src/main.rs)

```rust
// src/main.rs
#![no_std]
#![no_main]

// Zephyr's Rust bindings (from zephyr-sys crate)
use zephyr::prelude::*;

// Zephyr entry point macro
#[zephyr::entry]
fn main() -> i32 {
    // Zephyr's printk (not libc printf)
    zephyr::printk!("Hello from Rust on nRF54LM20!\r\n");

    // Access GPIO via Zephyr's device API
    let led = Device::get_binding("led0").unwrap();
    gpio_pin_configure(&led, 0, GPIO_OUTPUT_ACTIVE);
    
    loop {
        gpio_pin_set(&led, 0, 1);
        k_sleep(K_MSEC(500));
        gpio_pin_set(&led, 0, 0);
        k_sleep(K_MSEC(500));
    }
}
```

### 4. Build and Flash Commands

```bash
# 1. Set up environment (from Day 2)
source zephyr/zephyr-env.sh

# 2. Build with west (uses CMake under the hood)
west build -b nrf54lm20dk/nrf54lm20/cpuapp \
    -d build \
    -- \
    -DRUST_TARGET=thumbv8m.main-zephyr-eabi

# 3. Flash using nrfjprog (Nordic's tool)
nrfjprog --family NRF54 \
    --program build/zephyr/zephyr.hex \
    --sectorerase \
    --reset

# 4. Monitor UART output (optional)
screen /dev/ttyACM0 115200
```

### 5. Key Build Output

```
-- west build: generating build system
-- Found Rust toolchain: rustc 1.72.0 (nightly)
-- Using Zephyr target: thumbv8m.main-zephyr-eabi
-- Linking Rust library: rust_app
-- Generating hex: build/zephyr/zephyr.hex
Build complete.
```

## Common Pitfalls & Gotchas

### 1. Wrong Target Triple
The standard `thumbv8m.main-none-eabihf` target won't link with Zephyr. You **must** use Zephyr's custom target spec file. Symptoms: linker errors about missing `_start` or `__aeabi_*` functions. Fix: ensure `TARGET_SPEC_FILE` points to the correct JSON in your `CMakeLists.txt`.

### 2. Missing `#[zephyr::entry]` Macro
If you use `#[no_mangle] pub extern "C" fn main()` directly, Zephyr won't initialize its kernel before calling your code. The `#[zephyr::entry]` macro inserts the proper Zephyr initialization sequence. Without it, `printk` and `k_sleep` will crash or hang.

### 3. Flash Address Mismatch
The nRF54LM20 has a secure/non-secure partition. If you flash to the wrong region (e.g., secure when your app is non-secure), the bootloader will reject the image. Always use `--family NRF54` with `nrfjprog` and ensure your `prj.conf` has `CONFIG_TRUSTED_EXECUTION_NONSECURE=y` for user applications.

## Try It Yourself

1. **Build the Blinky**: Create a new Zephyr project with the CMake and Rust files above. Build for `nrf54lm20dk/nrf54lm20/cpuapp` and verify the hex file is generated in `build/zephyr/`.

2. **Flash and Observe**: Flash the binary to your nRF54LM20 DK using `nrfjprog`. Connect a serial terminal (115200 baud) and confirm you see "Hello from Rust on nRF54LM20!" and the LED blinks.

3. **Add a Second Thread**: Modify `main.rs` to spawn a Zephyr thread using `k_thread_create` that toggles a different GPIO. Build, flash, and verify both LEDs blink at different rates.

## Next Up

Tomorrow I'll tackle **Devicetree Bindings in Rust: Accessing Zephyr DT Nodes** — how to read GPIO, SPI, and UART configurations from the devicetree directly in Rust, without hardcoding pin numbers.
