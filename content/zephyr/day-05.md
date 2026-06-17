---
title: "Day 05: Building & Flashing: west build, flash, debug"
date: 2026-06-17
tags: ["til", "zephyr", "west", "build", "flashing"]
---

## What I Explored Today

Today I dug into the Zephyr build system and its primary tool, `west`. While `west build` looks like a simple wrapper around CMake and Ninja, it handles a surprising amount of complexity: board-specific hardware configuration, device tree compilation, Kconfig symbol resolution, and linker script generation. I spent the morning tracing through a build to understand exactly what happens under the hood, then moved on to flashing and debugging workflows that every embedded engineer needs to have muscle memory for.

## The Core Concept

Zephyr's build system is not just "CMake with a wrapper." The `west` tool orchestrates a multi-stage pipeline that transforms your application source, board definition, and configuration into a flashable binary. Understanding this pipeline is essential because when something breaks—and it will—you need to know where to look.

The pipeline works like this:

1. **Configuration phase**: `west build` invokes CMake, which reads `CMakeLists.txt`, discovers the board (via `-b` or `BOARD`), processes the device tree (`*.dts` files), and resolves Kconfig symbols into `autoconf.h`. This generates the build directory with all configuration headers.

2. **Compilation phase**: Ninja (the actual build system) compiles source files with the correct flags, including the generated `-include` directives for Kconfig and devicetree macros.

3. **Linking and post-processing**: The final ELF is linked, then converted to the target format (HEX, BIN, or UF2). Zephyr also runs `west sign` if needed for secure boot.

4. **Flashing**: `west flash` reads the board's flash runner (from the board definition) and invokes the appropriate tool—OpenOCD, pyOCD, JLink, dfu-util, or something custom.

The key insight: `west` is not doing the heavy lifting itself. It's a meta-tool that delegates to CMake, Ninja, and flash runners. This means you can always drop down to those tools if `west` isn't giving you enough control.

## Key Commands / Configuration / Code

### Basic build and flash

```bash
# Build for the nRF52840 DK
west build -b nrf52840dk_nrf52840 app/ -d build/nrf52840

# Build with a specific configuration overlay
west build -b nrf52840dk_nrf52840 app/ -- -DOVERLAY_CONFIG=overlay-debug.conf

# Flash the previously built binary
west flash -d build/nrf52840

# Flash with a specific runner (override board default)
west flash -d build/nrf52840 --runner jlink
```

### Debugging session

```bash
# Start a debug server and connect GDB
west debug -d build/nrf52840

# Or for a more manual approach:
# Start OpenOCD in one terminal
west build -b nrf52840dk_nrf52840 app/ -t openocd
# Then in another terminal:
arm-none-eabi-gdb build/nrf52840/zephyr/zephyr.elf
(gdb) target remote :3333
(gdb) monitor reset halt
(gdb) load
(gdb) break main
(gdb) continue
```

### Build configuration inspection

```bash
# See what Kconfig symbols were actually set
west build -t menuconfig  # Interactive configuration
west build -t guiconfig   # GUI configuration (if installed)

# Dump the final configuration
west build -t config-split
# Look at build/<board>/zephyr/.config for the full resolved config

# See the generated devicetree
cat build/<board>/zephyr/zephyr.dts
```

### Custom CMake targets

```cmake
# In your app's CMakeLists.txt, you can add custom post-build steps
add_custom_command(TARGET app POST_BUILD
    COMMAND ${CMAKE_OBJCOPY} -O binary
        ${ZEPHYR_BINARY_DIR}/zephyr.elf
        ${ZEPHYR_BINARY_DIR}/myapp.bin
    COMMENT "Generating raw binary"
)
```

## Common Pitfalls & Gotchas

1. **The `-d` flag is your friend, but easy to forget**: If you build without `-d`, `west` uses `build/` by default. If you then build for a different board without cleaning, you'll get stale artifacts. Always use `-d build/<board>` to keep builds separate. When things get weird, `rm -rf build/` and rebuild.

2. **Flash runner detection fails silently**: `west flash` might succeed but actually do nothing if the runner can't find your debug probe. Always check the output for "Flashing completed successfully" vs "Could not connect to target." I've wasted hours debugging code that was never actually flashed. Add `west flash -v` for verbose output.

3. **Device tree overlays not applied**: If you add a `.overlay` file but don't see your changes in `zephyr.dts`, you probably forgot to set `DTC_OVERLAY_FILE` or name it correctly. The file must be named `<board>.overlay` in your app directory, or you must explicitly pass it: `west build -- -DDTC_OVERLAY_FILE=my.overlay`. Check `build/<board>/zephyr/zephyr.dts.preprocessed` to see the merged tree.

## Try It Yourself

1. **Build for two different boards**: Create a simple blinky app, then build it for both an nRF52840 DK and a STM32 Nucleo board. Use separate build directories (`-d build/nrf`, `-d build/stm32`). Compare the generated `zephyr.dts` files to see how the hardware differs.

2. **Add a custom flash runner**: Create a shell script that copies your binary to a mounted USB drive (for UF2 bootloaders). Register it as a custom runner by setting `BOARD_FLASH_RUNNER` in your board's `Kconfig.defconfig`. Then test `west flash` with your custom runner.

3. **Debug a hard fault**: Write code that deliberately triggers a hard fault (e.g., divide by zero, or dereference NULL). Build with `CONFIG_DEBUG=y` and `CONFIG_DEBUG_INFO=y`, then use `west debug` to catch the fault and examine the call stack with `backtrace` in GDB.

## Next Up

Tomorrow we dive into threads: `k_thread_create`, priorities, and scheduling. We'll build a multi-threaded application, understand the scheduler's preemptive and cooperative modes, and learn why priority inversion is still a thing even with a modern RTOS.
