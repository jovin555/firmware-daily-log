---
title: "Day 25: Twister: Zephyr CI Test Runner for Multiple Boards"
date: 2026-07-07
tags: ["til", "hil-testing", "twister", "zephyr", "ci"]
---

## What I Explored Today

Today I dove into Twister, Zephyr's official test runner and CI orchestrator. Twister is the backbone of Zephyr's continuous integration pipeline, capable of building, flashing, and running test suites across dozens of hardware targets in parallel. Unlike ad-hoc test scripts, Twister provides a structured framework for defining test cases, managing board-specific configurations, and collecting results in a standardized format. I set up a multi-board test environment with a Nordic nRF52840 DK and an STM32 Nucleo-F401RE, running the same test suite on both to validate cross-platform behavior.

## The Core Concept

Twister solves a fundamental problem in embedded CI: how do you reliably test firmware across multiple hardware targets without manual intervention? The naive approach—writing custom shell scripts for each board—quickly becomes unmaintainable as your board farm grows. Twister abstracts away the hardware details through a board database (stored in `boards/`), a test specification language (YAML testcase files), and a hardware map (`.hwmap` file) that describes which boards are connected to which serial ports and debuggers.

The key insight is that Twister treats each test as a self-contained unit with explicit dependencies, timeouts, and platform filters. When you run `twister --platform nrf52840dk_nrf52840 --platform nucleo_f401re`, it:
1. Parses all testcases in your application or Zephyr tree
2. Filters tests that support both platforms
3. Builds each test for each platform in parallel (using CMake and west)
4. Flashes each board using the configured debugger (OpenOCD, pyOCD, JLink, etc.)
5. Captures serial output, compares against expected results, and reports pass/fail

This is a massive productivity boost. Instead of manually flashing five boards and watching serial terminals, you run one command and get a consolidated report. Twister also integrates with hardware-in-the-loop (HIL) setups, where physical boards are connected to a host machine via USB or Ethernet, and the test runner manages the entire lifecycle.

## Key Commands / Configuration / Code

### 1. Test Case Definition (`tests/hello_world/testcase.yaml`)

```yaml
# tests/hello_world/testcase.yaml
tests:
  hello_world.basic:
    # Tags help filter tests in CI pipelines
    tags: ["hello", "basic"]
    # Platform filter: only run on these boards
    platform_allow: nrf52840dk_nrf52840 nucleo_f401re
    # Timeout in seconds before test is killed
    timeout: 30
    # Type of test: 'integration' for HIL, 'unit' for native
    type: integration
    # Expected output pattern (regex) in serial console
    harness: console
    harness_config:
      type: one_line
      regex:
        - "Hello World! (.*)"
```

### 2. Hardware Map (`twister_hwmap.yaml`)

```yaml
# twister_hwmap.yaml — maps board IDs to physical connections
# This file tells Twister which boards are available and how to reach them
boards:
  - id: "nrf52840dk_1"
    platform: nrf52840dk_nrf52840
    # Serial port for console output
    serial: /dev/ttyACM0
    # Debug probe connection (OpenOCD config)
    probe: "nrf52"
    # Optional: runner type (west flash runner)
    runner: nrfjprog
  - id: "nucleo_f401re_1"
    platform: nucleo_f401re
    serial: /dev/ttyACM1
    probe: "stlink"
    runner: openocd
```

### 3. Running Twister

```bash
# Basic run on two platforms, using hardware map
twister \
  --platform nrf52840dk_nrf52840 \
  --platform nucleo_f401re \
  --hardware-map twister_hwmap.yaml \
  --testsuite-root tests/hello_world \
  --output-dir twister-out \
  --verbose

# Run only integration tests (HIL)
twister --integration \
  --hardware-map twister_hwmap.yaml \
  --output-dir twister-out

# Generate JUnit XML report for CI tools like Jenkins/GitLab
twister --integration \
  --hardware-map twister_hwmap.yaml \
  --report-suffix ci_run \
  --output-dir twister-out
```

### 4. Test Source Code (`tests/hello_world/src/main.c`)

```c
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

void main(void)
{
    printk("Hello World! %s\n", CONFIG_BOARD);
    // Twister will wait for this pattern and capture the board name
    // If the pattern doesn't appear within timeout, test fails
}
```

## Common Pitfalls & Gotchas

### 1. Serial Port Permissions and Race Conditions
Twister opens serial ports to capture output, but if your user doesn't have `dialout` group membership, the test will hang silently. Always verify with `ls -l /dev/ttyACM*` and `groups $USER`. Additionally, if two boards share the same USB-to-serial adapter (e.g., via a hub), Twister may get confused. Use `udev` rules to create persistent symlinks based on USB serial numbers.

### 2. Timeout Mismatches Between Test and Hardware
A common failure mode: your test has a 30-second timeout, but the board takes 45 seconds to boot due to a slow flash or a long initialization sequence. Twister kills the test prematurely. Always add a safety margin—I use 2x the measured boot time. For slow boards, consider adding `timeout: 120` in the testcase YAML.

### 3. Platform Filtering Is Not Optional
If you omit `platform_allow` or `platform_exclude`, Twister will try to build and run the test on *every* platform in your Zephyr tree. For a full Zephyr installation with 500+ boards, this takes hours and will fail on platforms that don't have the required drivers. Always explicitly list supported platforms, or use `--platform` flags on the command line to restrict the run.

## Try It Yourself

1. **Create a minimal test suite**: Write a test that prints the board name and passes. Run it on two different boards using `twister --platform <board1> --platform <board2>`. Verify the output in `twister-out/twister.log` shows both platforms as "PASSED".

2. **Add a deliberate failure**: Modify the test to print a different string than what the regex expects. Run Twister and observe the "FAILED" status. Check the serial log in `twister-out/<board>/<test_name>/device.log` to see what was actually printed.

3. **Set up a hardware map**: Create a `twister_hwmap.yaml` for your own boards. Use `west flash` to confirm the runner and serial port are correct, then run `twister --integration --hardware-map twister_hwmap.yaml` to validate the entire pipeline.

## Next Up

Tomorrow, we'll get our hands dirty with OpenOCD and pyOCD—the two most common programmatic flash and debug tools. You'll learn how to flash firmware from the command line without a full IDE, set breakpoints via GDB scripts, and integrate these tools into your CI pipeline for automated flashing and debugging. See you then.
