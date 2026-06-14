---
title: "Day 02: Project Structure: CMakeLists, prj.conf & Kconfig"
date: 2026-06-14
tags: ["til", "zephyr", "kconfig", "cmake"]
---

## What I Explored Today

Today I dug into the three files that form the backbone of every Zephyr application: `CMakeLists.txt`, `prj.conf`, and the Kconfig system. While Zephyr's build system can feel like a maze of macros and configuration options, understanding how these files interact is the key to controlling everything from which drivers are compiled to how much RAM your application consumes. I spent the afternoon tracing how a simple `CONFIG_GPIO=y` in `prj.conf` propagates through Kconfig trees and ultimately decides whether `gpio.c` gets linked into my binary.

## The Core Concept

Zephyr uses a two-stage build system. First, CMake processes your project structure and generates build files. Then, the Kconfig system resolves all configuration symbols into a single `.config` file that controls conditional compilation. The `prj.conf` file is your application's configuration overlay — it sets the values you care about, while Kconfig handles the dependency resolution and default values.

The reason this matters: Zephyr is modular by design. You don't get a monolithic kernel with everything compiled in. Instead, you declare what your application needs (e.g., "I need GPIO, I2C, and a UART console"), and the build system only compiles the necessary source files. This keeps flash footprints small — critical for constrained MCUs with 32KB or 64KB of flash.

## Key Commands / Configuration / Code

### Minimal CMakeLists.txt for a Zephyr Application

```cmake
# CMakeLists.txt - Every Zephyr app needs this
cmake_minimum_required(VERSION 3.20.0)

# Find and load the Zephyr build system
# This sets up all the infrastructure: toolchain, board config, Kconfig
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

# Define your application source files
# The name "my_app" becomes your executable target
project(my_app)

# Add all source files in the current directory
target_sources(app PRIVATE src/main.c src/sensor.c)
```

### prj.conf — Your Application's Configuration Overlay

```kconfig
# prj.conf - Application-specific Kconfig overrides
# These values override defaults from Kconfig.defconfig files

# Enable GPIO subsystem
CONFIG_GPIO=y

# Enable I2C for sensor communication
CONFIG_I2C=y

# Set console to UART, not USB or semihosting
CONFIG_CONSOLE=y
CONFIG_UART_CONSOLE=y

# Reduce logging to save flash (INFO only, no DEBUG)
CONFIG_LOG=y
CONFIG_LOG_DEFAULT_LEVEL=3  # 0=OFF, 1=ERR, 2=WRN, 3=INF, 4=DBG

# Set stack size for the main thread (default is often too small)
CONFIG_MAIN_STACK_SIZE=2048
```

### How Kconfig Resolution Works

When you run `west build -b <board> .`, the build system:

1. Loads the board's `Kconfig.defconfig` (e.g., `boards/arm/nrf52840dk_nrf52840/Kconfig.defconfig`)
2. Loads the SoC's `Kconfig.defconfig` (e.g., `soc/arm/nordic_nrf/nrf52/Kconfig.defconfig`)
3. Loads architecture defaults (`arch/arm/core/Kconfig.defconfig`)
4. Applies your `prj.conf` overrides
5. Resolves dependencies (e.g., `CONFIG_I2C=y` might force `CONFIG_GPIO=y`)
6. Generates `build/zephyr/.config` and `build/zephyr/include/generated/autoconf.h`

You can inspect the resolved configuration with:

```bash
# View the full resolved configuration
west build -t menuconfig

# Or dump it to stdout
west build -t config

# See what changed from defaults
west build -t config_diff
```

## Common Pitfalls & Gotchas

### 1. Forgetting `prj.conf` is NOT a Kconfig file
`prj.conf` uses the *old* Kconfig syntax (`CONFIG_FOO=y`), not the new Kconfig syntax (`config FOO`). You cannot define new Kconfig symbols in `prj.conf` — you can only set values for symbols that already exist in the Kconfig tree. If you misspell a symbol, Zephyr silently ignores it. Always run `west build -t config` to verify your settings took effect.

### 2. Dependency Hell with Implicit Selections
Some Kconfig symbols have `select` statements that force-enable other symbols. For example, enabling `CONFIG_I2C` on an nRF52840 might automatically select `CONFIG_GPIO` and `CONFIG_CLOCK_CONTROL`. If you later try to disable GPIO to save space, Kconfig will either refuse or silently re-enable it. Use `menuconfig` to see the dependency chain.

### 3. CMakeLists.txt Path Sensitivity
Zephyr's `target_sources()` uses relative paths from the CMakeLists.txt location. If you have source files in a subdirectory, you must either use `src/sensor.c` or add the subdirectory with `add_subdirectory()`. A common mistake is putting `sensor.c` in `src/sensor/` and referencing it as `sensor.c` — CMake won't find it.

## Try It Yourself

1. **Inspect the resolved configuration**: Create a minimal Zephyr app with `CONFIG_GPIO=y` in `prj.conf`. Build for `nrf52840dk_nrf52840` and run `west build -t config_diff`. Note which additional symbols were automatically enabled by Kconfig dependencies.

2. **Break the build with a typo**: Deliberately misspell a Kconfig symbol (e.g., `CONFIG_GIPO=y`) in `prj.conf`. Build the project and observe that Zephyr does NOT report an error. Then run `west build -t config` and grep for `GIPO` to confirm it was ignored.

3. **Reduce flash footprint**: Start with a default application that enables logging at debug level. Change `CONFIG_LOG_DEFAULT_LEVEL` from 4 to 2 in `prj.conf`. Rebuild and compare the resulting binary sizes using `west build -t ram_report` and `west build -t rom_report`.

## Next Up

Tomorrow we tackle Devicetree in Zephyr: DTS, DTSI & Overlays. We'll explore how hardware descriptions (pin muxes, peripheral addresses, interrupt numbers) are separated from driver code, and how you can override board definitions without touching vendor files.
