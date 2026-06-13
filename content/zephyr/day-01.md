---
title: "Day 01: Introduction to Zephyr: Architecture & the West Build System"
date: 2026-06-13
tags: ["til", "zephyr", "zephyr", "rtos", "west"]
---

## What I Explored Today

I finally dove into Zephyr RTOS, and the first thing that struck me is how different it feels from bare-metal or FreeRTOS work. Zephyr isn't just a kernel — it's a complete ecosystem with its own build system, device tree integration, and a modular architecture that scales from tiny Cortex-M0 parts to multicore application processors. Today I focused on understanding the high-level architecture and, more practically, getting the `west` build system to do what I wanted.

## The Core Concept

Zephyr's architecture is built around three pillars: the kernel, the hardware abstraction layer (HAL), and the build system. The kernel provides the familiar RTOS primitives — threads, semaphores, message queues — but with a twist: everything is configurable at compile time through Kconfig. This means you can strip out features you don't need, producing a binary that fits in 8 KB of flash if you're careful.

The real magic, though, is the build system. Zephyr uses `west` (Zephyr's meta-tool) on top of CMake. West manages multi-repo projects, fetches toolchains, and orchestrates the build. Under the hood, CMake handles the actual compilation, but west adds the "Zephyr layer" — board detection, device tree processing, and Kconfig symbol resolution. The key insight is that west is not a replacement for CMake; it's a project management tool that calls CMake for you.

The device tree is another critical piece. Zephyr uses devicetree (DT) to describe hardware — which UART is on what pins, how much RAM the chip has, which peripherals are available. This is compiled into the final binary, so your application code can reference hardware by label (`&uart0`) rather than hardcoded addresses. This makes porting between boards dramatically easier.

## Key Commands / Configuration / Code

First, install west and get the Zephyr source:

```bash
# Install west via pip
pip3 install west

# Initialize a workspace (creates a .west directory)
west init ~/zephyrproject
cd ~/zephyrproject

# Download all Zephyr modules (hal, drivers, etc.)
west update
```

Export Zephyr's CMake package so CMake can find it:

```bash
west zephyr-export
```

Now build a sample. The `-b` flag specifies the board. Let's build the blinky sample for the nRF52840 DK:

```bash
cd ~/zephyrproject/zephyr
west build -b nrf52840dk_nrf52840 samples/basic/blinky
```

The output goes to `build/zephyr/zephyr.elf` (or `.hex`). To clean and rebuild:

```bash
west build -t clean
west build -b nrf52840dk_nrf52840 samples/basic/blinky
```

To see what boards are available:

```bash
west boards
```

Now, let's look at a minimal application. Create a file `src/main.c`:

```c
#include <zephyr/kernel.h>
#include <zephyr/drivers/gpio.h>

/* Get the LED0 devicetree alias */
#define LED0_NODE DT_ALIAS(led0)
static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);

void main(void)
{
    /* Check if the GPIO controller is ready */
    if (!device_is_ready(led.port)) {
        return;
    }

    /* Configure the pin as output */
    gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);

    while (1) {
        gpio_pin_toggle_dt(&led);
        k_msleep(1000);
    }
}
```

And the corresponding `prj.conf`:

```bash
# Enable GPIO subsystem
CONFIG_GPIO=y
```

The `CMakeLists.txt` for this app:

```cmake
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(blinky)

target_sources(app PRIVATE src/main.c)
```

Build it:

```bash
west build -b nrf52840dk_nrf52840 . -p always
```

The `-p always` flag forces a pristine build (cleans first).

## Common Pitfalls & Gotchas

1. **West workspace confusion**: If you run `west build` outside a west-managed directory, it fails with "fatal: not a west workspace". Always run from inside the `zephyrproject` directory (or wherever you ran `west init`). The `.west` directory must exist in a parent path.

2. **Board name mismatches**: `west boards` shows names like `nrf52840dk_nrf52840`, but some documentation uses shorthand like `nrf52840dk`. Always use the exact name from `west boards`. Getting this wrong gives cryptic CMake errors about missing board definitions.

3. **Missing toolchain**: If you see "No toolchain found" errors, you need to set `ZEPHYR_TOOLCHAIN_VARIANT` and point to your toolchain. For ARM GCC:

   ```bash
   export ZEPHYR_TOOLCHAIN_VARIANT=gnuarmemb
   export GNUARMEMB_TOOLCHAIN_PATH=/path/to/gcc-arm-none-eabi
   ```

   Or use the Zephyr SDK for a smoother experience.

## Try It Yourself

1. **Build for a different board**: Pick a board you have (or emulate one like `qemu_cortex_m3`) and build the `samples/basic/blinky` sample. Flash it and verify the LED blinks.

2. **Modify the blink rate**: In the blinky sample, change `k_msleep(1000)` to `k_msleep(500)` and rebuild. Observe the faster blink. This teaches you the edit-build-flash cycle.

3. **Explore Kconfig**: Run `west build -t menuconfig` on your blinky build. Navigate to `Device Drivers -> GPIO` and see how `CONFIG_GPIO` is enabled. This is your first look at Zephyr's configuration system.

## Next Up

Tomorrow, we'll dissect the project structure: how `CMakeLists.txt`, `prj.conf`, and Kconfig work together to define your application. We'll build a custom project from scratch and understand why Zephyr's build system is both powerful and occasionally infuriating.
