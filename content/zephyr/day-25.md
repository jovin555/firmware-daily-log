---
title: "Day 25: Ztest Framework & Unit Tests"
date: 2026-07-07
tags: ["til", "zephyr", "ztest", "testing"]
---

## What I Explored Today

Today I dug into Zephyr's native test framework, **ztest**, and wrote my first real unit tests for a sensor driver. After weeks of building drivers and subsystems, I realized my code was fragile—one wrong register write and the whole stack could silently fail. Ztest gives us a structured way to validate individual functions, mock hardware dependencies, and catch regressions before they hit the target. I walked through setting up a test suite, writing test cases with assertions, and running them both natively on my host machine and on a QEMU emulated board.

## The Core Concept

Why do we need a dedicated test framework in an RTOS? Because embedded testing is fundamentally different from desktop testing. You can't just `printf` and hope—you need deterministic control over timing, hardware state, and interrupt context. Ztest provides:

- **Test lifecycle hooks** (`test_setup`, `test_teardown`) to initialize and clean up state per test
- **Assertion macros** that halt on failure with detailed diagnostics (file, line, actual vs expected)
- **Test grouping** via `ztest_test_suite` to organize related tests
- **Native execution** on your host PC using the `native_posix` board, which simulates kernel objects and drivers without real hardware

The real power is that you can test driver logic, state machines, and error handling without flashing a board. This means your CI pipeline can run thousands of tests in seconds, catching bugs like null pointer dereferences, buffer overflows, or incorrect register masks before they ever reach production hardware.

## Key Commands / Configuration / Code

### 1. Project Structure for a Test Suite

Zephyr tests live under `tests/` in your application or module. For a sensor driver, I created:

```
tests/drivers/sensor_xyz/
├── CMakeLists.txt
├── prj.conf
└── src/
    └── test_sensor_xyz.c
```

### 2. CMakeLists.txt

```cmake
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(sensor_xyz_test)

# Add the test source file
FILE(GLOB app_sources src/*.c)
target_sources(app PRIVATE ${app_sources})

# Link the ztest library (automatically included by Zephyr)
# No explicit ztest dependency needed—Zephyr's test infrastructure handles it
```

### 3. prj.conf (minimal)

```kconfig
# Enable ztest framework
CONFIG_ZTEST=y
# Use minimal kernel for faster native execution
CONFIG_MINIMAL_LIBC=y
# Reduce log level to avoid noise during tests
CONFIG_LOG_DEFAULT_LEVEL=1
```

### 4. Test Source (test_sensor_xyz.c)

```c
#include <zephyr/ztest.h>
#include <zephyr/drivers/sensor.h>
#include "sensor_xyz.h"  // Our driver header

/* Test fixture: a mock sensor device */
static const struct device *sensor_dev;

/* Called before each test in the suite */
static void *test_setup(void)
{
    /* Get the sensor device binding (simulated in native_posix) */
    sensor_dev = DEVICE_DT_GET(DT_NODELABEL(sensor_xyz));
    zassert_not_null(sensor_dev, "Sensor device not found");
    return NULL;
}

/* Test: sensor should initialize with correct ID register */
ZTEST(sensor_xyz_tests, test_init_id)
{
    uint8_t id;
    int ret;

    ret = sensor_xyz_read_register(sensor_dev, REG_CHIP_ID, &id);
    zassert_equal(ret, 0, "Failed to read chip ID (err %d)", ret);
    zassert_equal(id, 0x5A, "Unexpected chip ID: got 0x%02x, expected 0x5A", id);
}

/* Test: sensor should reject invalid sample rate */
ZTEST(sensor_xyz_tests, test_invalid_sample_rate)
{
    int ret;

    ret = sensor_xyz_set_sample_rate(sensor_dev, 9999);  /* Out of range */
    zassert_equal(ret, -EINVAL, "Expected -EINVAL, got %d", ret);
}

/* Test: sensor should return valid temperature data */
ZTEST(sensor_xyz_tests, test_temperature_range)
{
    struct sensor_value temp;
    int ret;

    ret = sensor_sample_fetch(sensor_dev);
    zassert_equal(ret, 0, "Sample fetch failed (err %d)", ret);

    ret = sensor_channel_get(sensor_dev, SENSOR_CHAN_AMBIENT_TEMP, &temp);
    zassert_equal(ret, 0, "Channel get failed (err %d)", ret);

    /* Temperature should be between -40 and 85 °C */
    zassert_true(temp.val1 >= -40 && temp.val1 <= 85,
                 "Temperature %d out of expected range", temp.val1);
}

/* Register the test suite */
ZTEST_SUITE(sensor_xyz_tests, NULL, NULL, test_setup, NULL, NULL);
```

### 5. Building and Running

```bash
# Build for native_posix (runs on host)
west build -b native_posix tests/drivers/sensor_xyz

# Run the test binary
./build/zephyr/zephyr.exe

# Or run with twister (next day's topic) for automated execution
west twister -T tests/drivers/sensor_xyz --platform native_posix
```

Sample output:

```
Running TESTSUITE sensor_xyz_tests
===================================================================
START - test_init_id
 PASS - test_init_id in 0.002 seconds
START - test_invalid_sample_rate
 PASS - test_invalid_sample_rate in 0.001 seconds
START - test_temperature_range
 PASS - test_temperature_range in 0.003 seconds
===================================================================
Test suite sensor_xyz_tests succeeded
3 test(s) passed, 0 failed
```

## Common Pitfalls & Gotchas

1. **Forgetting to enable CONFIG_ZTEST in prj.conf**  
   Without this, the test macros expand to nothing, and your test suite silently compiles as an empty main(). Always double-check your .conf file—I wasted 20 minutes wondering why no tests ran.

2. **Using zassert macros outside of ZTEST() functions**  
   The assertion macros depend on internal test context. If you call `zassert_equal()` in a helper function that isn't invoked from a `ZTEST()` block, you'll get a linker error or undefined behavior. Keep assertions inside test functions or pass results back via return values.

3. **Assuming native_posix simulates all hardware**  
   Native_posix is great for logic tests, but it doesn't emulate real sensor I2C/SPI buses. For driver tests that need actual bus transactions, use QEMU with a simulated peripheral or write mock backends. I learned this when my "temperature range" test passed on native but failed on real hardware because the mock always returned 25°C.

## Try It Yourself

1. **Write a test for error handling**  
   Take any driver you've written (or a Zephyr sample driver) and add a test that verifies it returns `-ENODEV` when the device pointer is NULL. Use `zassert_equal(ret, -ENODEV, ...)`.

2. **Add a test fixture with setup/teardown**  
   Modify the example above to allocate a test buffer in `test_setup()`, fill it with known data, and verify the driver processes it correctly. Free the buffer in `test_teardown()`.

3. **Run your test suite on a different board**  
   Build the same test for `qemu_cortex_m3` and run it with `west build -b qemu_cortex_m3 ... && west build -t run`. Notice how the test output is identical—the framework abstracts the platform.

## Next Up

Tomorrow, we'll scale up from single test suites to **Twister: Automated Test Execution**. Twister is Zephyr's test runner that can build and execute thousands of tests across multiple boards, generate reports, and integrate with CI systems. We'll configure a test plan, run it in parallel, and see how to catch regressions across your entire codebase automatically.

*Keep your code tested, your assertions tight, and your CI green.*
