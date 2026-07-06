---
title: "Day 24: Logging Subsystem: LOG_MODULE_REGISTER"
date: 2026-07-06
tags: ["til", "zephyr", "logging", "debug"]
---

## What I Explored Today

Today I dug into the Zephyr logging subsystem's module registration mechanism. While I've been using `LOG_INF()` and friends for weeks, I never fully understood what `LOG_MODULE_REGISTER()` actually does under the hood. After tracing through the macro expansions and experimenting with different configurations, I now see how this single macro controls log filtering, runtime level changes, and even whether log messages cost any CPU cycles at all. It's the foundation every Zephyr developer should understand before shipping production firmware.

## The Core Concept

`LOG_MODULE_REGISTER()` is not just a boilerplate declaration — it's a compile-time and runtime contract between your source file and the logging subsystem. Every time you call `LOG_INF()` or `LOG_ERR()`, the system needs to know:

1. **Which module** this message belongs to (for filtering and identification)
2. **What the default log level** should be (compile-time optimization)
3. **Whether runtime level changes** are allowed (memory vs. flexibility trade-off)

The macro creates a static `struct log_source_const_data` (in ROM) and a `struct log_source_dynamic_data` (in RAM if runtime filtering is enabled). The compiler then uses the module ID to decide at compile time whether to even include the log call in the binary. If your module's compile-time level is `LOG_LEVEL_WRN` and you call `LOG_DBG()`, that call is **dead code eliminated** — zero overhead.

This is critical for resource-constrained systems. You can leave debug logging in your code, set the module to `LOG_LEVEL_OFF` for production, and the linker will discard those strings and calls. No conditional compilation (`#ifdef DEBUG`) needed.

## Key Commands / Configuration / Code

### Basic Registration (Most Common)

```c
#include <zephyr/logging/log.h>

/* Register module "my_driver" with default level INFO, no runtime filtering */
LOG_MODULE_REGISTER(my_driver, CONFIG_MY_DRIVER_LOG_LEVEL);

void my_driver_init(void)
{
    LOG_INF("Driver initialized, version %d.%d", 1, 0);  // Always compiled if level >= INF
    LOG_DBG("Register base: 0x%p", DEVICE_MMIO_GET(dev)); // Dead code unless level >= DBG
}
```

### With Runtime Level Control

```c
/* Enable runtime level changes (adds ~8 bytes RAM per module) */
LOG_MODULE_REGISTER(my_driver, CONFIG_MY_DRIVER_LOG_LEVEL);

/* Later, at runtime: */
log_filter_set(LOG_LEVEL_DBG, &log_const_my_driver, &log_dynamic_my_driver);
```

### Module-Level Kconfig (typical pattern)

```kconfig
# Kconfig.my_driver
config MY_DRIVER_LOG_LEVEL
    int "Log level for my_driver"
    default 3  # LOG_LEVEL_INF
    range 0 4  # OFF, ERR, WRN, INF, DBG
    help
      Compile-time log level for my_driver module.
```

### What the Macro Expands To (simplified)

```c
/* LOG_MODULE_REGISTER(my_driver, 3) expands to approximately: */

/* In ROM (const data) */
const struct log_source_const_data log_const_my_driver = {
    .name = "my_driver",
    .level = 3,  /* LOG_LEVEL_INF */
    .filters = NULL,
};

/* In RAM (dynamic data, only if CONFIG_LOG_RUNTIME_FILTERING=y) */
struct log_source_dynamic_data log_dynamic_my_driver = {
    .filters = {0},
};
```

## Common Pitfalls & Gotchas

### 1. Multiple Registrations in Same File

You cannot call `LOG_MODULE_REGISTER()` twice in the same translation unit. If you have multiple logical modules in one `.c` file, you must either split the file or use `LOG_MODULE_DECLARE()` for the secondary module and register it elsewhere.

```c
// WRONG: Two registrations in same file
LOG_MODULE_REGISTER(sensor_a, 4);
LOG_MODULE_REGISTER(sensor_b, 4);  // Linker error: duplicate symbol

// RIGHT: Register one, declare the other
LOG_MODULE_REGISTER(sensor_a, 4);
LOG_MODULE_DECLARE(sensor_b, 4);  // Just declares, no new source data
```

### 2. Forgetting to Set the Kconfig Default

If you write `LOG_MODULE_REGISTER(my_mod, CONFIG_MY_MOD_LOG_LEVEL)` but never define `CONFIG_MY_MOD_LOG_LEVEL` in Kconfig, the macro will expand with a zero (LOG_LEVEL_OFF). Your logs silently disappear. Always add a Kconfig default, or use a hardcoded level during development:

```c
/* Safer during bring-up: */
LOG_MODULE_REGISTER(my_mod, 4);  // LOG_LEVEL_DBG during development
```

### 3. Runtime Filtering Memory Cost

Enabling `CONFIG_LOG_RUNTIME_FILTERING` adds a `uint32_t` per registered module. On a chip with 16 KB RAM and 50 modules, that's 200 bytes — not huge, but it's permanent. More importantly, it prevents the compiler from dead-code-eliminating log calls at levels below the runtime filter. If you never change filters at runtime, leave this feature off.

## Try It Yourself

1. **Trace the macro expansion**: In your project, add `LOG_MODULE_REGISTER(my_test, 4)` to a new file, then build with `make VERBOSE=1` and inspect the preprocessor output (`build/zephyr/misc/generated/syscalls.c`). Look for `log_const_my_test` and `log_dynamic_my_test`.

2. **Measure dead code elimination**: Create a module with `LOG_MODULE_REGISTER(my_mod, 2)` (ERR only). Add `LOG_DBG("expensive string %d", compute_heavy())`. Build, check the binary size. Then change the level to 4 (DBG) and rebuild. Compare `.text` and `.rodata` sizes with `arm-none-eabi-size`.

3. **Implement runtime filter switching**: Enable `CONFIG_LOG_RUNTIME_FILTERING`, register a module with level 4, and add a shell command that calls `log_filter_set()` to toggle between ERR and DBG. Verify that debug messages appear/disappear without rebooting.

## Next Up

Tomorrow we'll dive into the **Ztest Framework & Unit Tests** — how to write deterministic, repeatable tests for your Zephyr drivers and application logic, including mocking hardware dependencies and running tests on both host and target.
