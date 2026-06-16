---
title: "Day 04: Kconfig Deep Dive: Symbols, Dependencies & Menuconfig"
date: 2026-06-16
tags: ["til", "zephyr", "kconfig", "configuration"]
---

## What I Explored Today

After three days of building and flashing, I realized I was treating Kconfig like a magic black box — flipping switches without understanding the wiring. Today I went deep into Zephyr's configuration system: how symbols are defined, how dependencies propagate, and how to navigate the menuconfig interface effectively. I learned that Kconfig isn't just a configuration file; it's a declarative language for managing compile-time decisions across hundreds of drivers, subsystems, and board variants.

## The Core Concept

Zephyr's Kconfig system solves a fundamental problem: how do you configure a modular RTOS that must run on wildly different hardware (from Cortex-M0 to x86) while keeping the binary size small? The answer is a tree of boolean and integer symbols with explicit dependency chains.

Every Kconfig symbol (like `CONFIG_I2C` or `CONFIG_SENSOR`) has three critical attributes:
- **Type**: `bool`, `int`, `hex`, or `string`
- **Prompt**: The human-readable text shown in menuconfig
- **Dependencies**: `depends on` and `select` statements that enforce consistency

The key insight: `depends on` creates a *requirement* — the symbol is invisible unless its dependency is met. `select` creates a *reverse dependency* — enabling this symbol automatically enables another. Understanding this distinction prevents the most common configuration errors.

## Key Commands / Configuration / Code

### 1. Symbol Definition (in Kconfig files)

```kconfig
# drivers/sensor/Kconfig
config SENSOR
    bool "Sensor drivers support"
    help
      Enable sensor subsystem. Required for all sensor drivers.

config BMP280
    bool "BMP280 temperature/pressure sensor"
    depends on SENSOR
    select I2C
    help
      Bosch BMP280 sensor driver. Requires I2C bus.
```

Here, `BMP280` depends on `SENSOR` being enabled, and selecting `BMP280` automatically selects `I2C`. This is a real pattern used in Zephyr's sensor drivers.

### 2. Menuconfig Navigation

```bash
# Launch the interactive configuration tool
west build -t menuconfig -b nrf52840dk_nrf52840 samples/basic/blinky

# Inside menuconfig:
# - Use arrow keys to navigate
# - Enter to enter a menu
# - Space to toggle bool symbols (M for modules)
# - / to search for symbols
# - ? to see symbol help and dependencies
# - Z to see all symbols (including invisible ones)
```

The `?` key is your best friend. Press it on any symbol to see:
- Current value
- Direct dependencies (the `depends on` chain)
- Reverse dependencies (what `select`s this symbol)
- Default value and range (for int/hex)

### 3. Checking Configuration from Code

```c
// In your application code
#include <zephyr/kernel.h>

void check_config(void) {
    // IS_ENABLED() is a macro that evaluates at compile time
    if (IS_ENABLED(CONFIG_I2C)) {
        printk("I2C is enabled\n");
    }

    // For integer symbols, use the macro directly
    #if CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE > 2048
    #warning "Workqueue stack is larger than 2KB"
    #endif
}
```

### 4. Overriding Defaults in `prj.conf`

```conf
# prj.conf — project-level configuration
# Enable sensor subsystem
CONFIG_SENSOR=y

# Enable BMP280 driver
CONFIG_BMP280=y

# I2C is automatically selected by BMP280, but we set bus speed
CONFIG_I2C=y
CONFIG_I2C_NRFX_TWIM0=y
```

Note: You don't need `CONFIG_I2C=y` if `BMP280` selects it, but being explicit helps readability.

## Common Pitfalls & Gotchas

### 1. The "Invisible Symbol" Trap
You add `CONFIG_MY_FEATURE=y` to `prj.conf`, but `menuconfig` shows it as `n`. The symbol has an unmet dependency. Run `west build -t menuconfig`, press `/`, search for your symbol, and check "Direct dependencies" — they're listed in red if unmet.

### 2. `select` vs `depends on` Confusion
`select` forces a symbol ON, but it does *not* check if that symbol's own dependencies are met. This can create broken configurations. Example: if `BMP280` selects `I2C`, but `I2C` depends on `HAS_HW_I2C` (a board-level symbol), and your board doesn't define it — you get a build error. Always verify dependency chains with `?` in menuconfig.

### 3. Overriding Board Defaults Incorrectly
Board Kconfig files (e.g., `boards/arm/nrf52840dk_nrf52840/Kconfig.defconfig`) set defaults. Your `prj.conf` overrides them, but only if the symbol isn't `fixed` (marked as `choice` or `range` with `option defconfig_list`). If a board forces `CONFIG_SERIAL=y`, you cannot disable it in `prj.conf`. Check the board's Kconfig file first.

## Try It Yourself

1. **Trace a dependency chain**: Open `samples/basic/blinky`, run `west build -t menuconfig`, search for `GPIO`, press `?`, and write down the full dependency chain (all symbols it `depends on` and all symbols that `select` it).

2. **Create a custom Kconfig fragment**: Add a file `my_overlay.conf` with `CONFIG_PRINTK=y` and `CONFIG_LOG=y`. Build with: `west build -b nrf52840dk_nrf52840 samples/hello_world -- -DOVERLAY_CONFIG=my_overlay.conf`. Verify the symbols are enabled in the build output.

3. **Break and fix a configuration**: In `prj.conf`, add `CONFIG_I2C=y` without enabling a board-specific I2C peripheral (like `CONFIG_I2C_NRFX`). Build and observe the error. Then fix it by adding the correct peripheral symbol.

## Next Up

Tomorrow, we'll move from configuration to execution: mastering the `west build`, `west flash`, and `west debug` workflow — including how to set breakpoints, inspect registers, and use Zephyr's built-in shell for runtime debugging.
