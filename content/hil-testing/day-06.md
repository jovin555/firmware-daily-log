---
title: "Day 06: Twister: Zephyr CI Test Runner for Multiple Boards"
date: 2026-06-18
tags: ["til", "hil-testing", "twister", "zephyr", "ci"]
---

## What I Explored Today

Today I dove into Twister, Zephyr's official test runner and CI orchestrator. After spending the past few days setting up individual HIL rigs, I needed a way to run the same integration tests across multiple board targets in a single command. Twister is the tool that does exactly that — it discovers test cases, builds for specified boards, flashes them, collects results, and reports failures. I wired it into our CI pipeline to run a suite of 12 integration tests across 4 ARM boards (nRF52840 DK, STM32F4 Discovery, STM32L4 IoT Node, and a custom board) in under 8 minutes.

## The Core Concept

Twister solves a fundamental problem in embedded CI: how do you test the same application logic across multiple hardware targets without writing per-board test scripts? The answer is a declarative test specification system combined with a hardware farm abstraction.

At its heart, Twister works like this:

1. **Test Discovery** — It scans your Zephyr application directory for `testcase.yaml` files that define test metadata (name, description, required hardware, timeout).
2. **Build Matrix** — For each discovered test, it builds the firmware for every board you specify (or all boards in your hardware map).
3. **Flash & Run** — Using a hardware map file (`--hardware-map`), it knows which physical boards are connected to which serial ports and debuggers. It flashes each board, runs the test, captures stdout, and checks for a pass/fail signature.
4. **Reporting** — Results go to console, JUnit XML (for CI), and a detailed JSON report.

The key insight is that Twister treats the test as a black box: your test must print `PROJECT EXECUTION SUCCESSFUL` (or `FAILED`) to stdout. Twister doesn't care *how* the test works internally — it just orchestrates the build-flash-run cycle.

## Key Commands / Configuration / Code

### Minimal testcase.yaml

Every Zephyr test needs this file in its directory:

```yaml
# tests/my_integration_test/testcase.yaml
tests:
  my_integration_test:
    type: integration
    tags: hil gpio i2c
    platform_allow: nrf52840dk_nrf52840 stm32f4_disco
    timeout: 60
    harness: console
    harness_config:
      type: one_line
      regex:
        - "ALL TESTS PASSED"
```

The `harness: console` tells Twister to watch serial output. The regex is what we consider a pass.

### Running Twister Locally

```bash
# Basic run on all boards in hardware map
west twister -T tests/my_integration_test/ \
             --hardware-map my_boards.yaml \
             --device-testing \
             --inline-logs

# Run only specific boards
west twister -T tests/ \
             --hardware-map my_boards.yaml \
             --device-testing \
             --platform nrf52840dk_nrf52840 \
             --platform stm32f4_disco

# Generate JUnit XML for CI
west twister -T tests/ \
             --hardware-map my_boards.yaml \
             --device-testing \
             --report-suffix $(date +%Y%m%d_%H%M) \
             --output-sync=line
```

### Hardware Map File (my_boards.yaml)

This is the critical piece that maps logical board names to physical connections:

```yaml
# my_boards.yaml
- id: nrf52840_dk_01
  platform: nrf52840dk_nrf52840
  runner: nrfjprog
  serial: /dev/ttyACM0
  connect: /dev/ttyACM0
  baud: 115200

- id: stm32f4_disco_01
  platform: stm32f4_disco
  runner: openocd
  serial: /dev/ttyACM1
  connect: /dev/ttyACM1
  baud: 115200
  openocd_config: board/stm32f4discovery.cfg
```

### Test Source Example (minimal)

```c
// tests/my_integration_test/src/main.c
#include <zephyr/ztest.h>

ZTEST(my_suite, test_gpio_toggle)
{
    const struct device *dev = DEVICE_DT_GET(DT_NODELABEL(my_gpio));
    zassert_true(device_is_ready(dev), "GPIO device not ready");
    
    gpio_pin_configure(dev, 13, GPIO_OUTPUT_ACTIVE);
    gpio_pin_set(dev, 13, 1);
    k_sleep(K_MSEC(100));
    gpio_pin_set(dev, 13, 0);
    
    printk("ALL TESTS PASSED\n");
}

ZTEST_SUITE(my_suite, NULL, NULL, NULL, NULL, NULL);
```

### CI Integration (GitHub Actions snippet)

```yaml
# .github/workflows/hil-tests.yml
jobs:
  twister-hil:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - name: Run Twister HIL tests
        run: |
          west twister -T tests/ \
            --hardware-map hardware_map.yaml \
            --device-testing \
            --output-sync=line \
            --report-suffix ${{ github.run_id }} \
            --junit-xml
      - name: Upload test results
        uses: actions/upload-artifact@v4
        with:
          name: twister-results
          path: twister-out/report.xml
```

## Common Pitfalls & Gotchas

### 1. Serial Port Contention
If two Twister instances (or other tools) try to open the same serial port, you get `[ERROR] Could not open serial device`. Always ensure your hardware map has unique `serial:` entries. On Linux, use `udevadm info -a -n /dev/ttyACM0` to get stable symlinks (e.g., `/dev/serial/by-id/`).

### 2. Timeout Mismatch
Your `timeout:` in `testcase.yaml` must be generous. Twister starts counting from when it begins flashing, not when the test starts running. A 30-second timeout is often too short for a board that takes 15 seconds to flash. I use `timeout: 120` for integration tests and rely on the test itself to fail fast.

### 3. Flashing Failures Are Silent
If a board is not connected or the debugger is flaky, Twister will report the test as "failed" but the error message is often just "No serial output received." Always run with `--inline-logs` during development to see the actual flash output. I also add a pre-check script that pings each board before running tests:

```bash
# pre_check.sh — run before twister
for port in /dev/ttyACM0 /dev/ttyACM1; do
  if [ ! -e "$port" ]; then
    echo "ERROR: $port not found"
    exit 1
  fi
done
```

## Try It Yourself

1. **Create a hardware map** for your lab bench. List 2-3 boards with their serial ports and debugger runners. Run `west twister --list-tests` to verify discovery works.

2. **Write a simple test** that toggles an LED and prints "ALL TESTS PASSED". Run it on two different boards using `--platform` flags. Observe how Twister parallelizes the builds but serializes the flashing.

3. **Break your test intentionally** (e.g., remove the print statement) and run again. Examine the JUnit XML output in `twister-out/` — note how Twister reports the failure reason and elapsed time.

## Next Up

Tomorrow we'll go deeper into the flash-and-debug cycle with **OpenOCD & pyOCD: Programmatic Flash & Debug**. We'll write scripts that flash firmware, attach GDB, set breakpoints, and extract register dumps — all without human intervention. This is the foundation for automated hardware-in-the-loop debugging in CI.
