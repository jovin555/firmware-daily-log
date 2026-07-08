---
title: "Day 26: Twister: Automated Test Execution"
date: 2026-07-08
tags: ["til", "zephyr", "twister", "ci"]
---

## What I Explored Today

Today I finally dug into Twister, Zephyr's official test runner and automation framework. After weeks of manually flashing boards and squinting at UART logs, I needed a repeatable way to run the growing test suite across multiple targets. Twister handles test discovery, cross-compilation, execution on hardware or simulators, and result reporting—all from a single command. It's the backbone of Zephyr's CI pipeline, and after today, I understand why.

## The Core Concept

Twister solves a fundamental problem: embedded projects have many configurations (boards, SoCs, drivers, subsystems) and testing every combination manually is impossible. Instead of writing ad-hoc shell scripts that hardcode build flags and flash commands, Twister provides a declarative framework.

At its heart, Twister does three things:
1. **Discovers tests** by scanning the Zephyr tree for `testcase.yaml` files
2. **Builds each test** for every matching board/platform, using the test's declared dependencies and filters
3. **Executes** the built binaries—either on real hardware via a runner, or on a simulator like QEMU or native_posix

The key insight is that Twister treats testing as a build-time concern. Each test is a Zephyr application with a `testcase.yaml` manifest that declares what it tests, what hardware it needs, and how to verify success. This makes tests portable across boards and reproducible in CI.

## Key Commands / Configuration / Code

### Running Twister

The simplest invocation runs all tests for a specific board:

```bash
# Run all tests for the nRF52840 DK on QEMU
twister -p qemu_cortex_m3 -T tests/ -v

# -p: platform/board target
# -T: test directory root (scans recursively for testcase.yaml)
# -v: verbose output
```

For hardware testing, you specify a runner script:

```bash
# Run on real hardware via pyOCD
twister -p nrf52840dk_nrf52840 -T tests/kernel -v \
  --device-testing --device-serial /dev/ttyACM0 \
  --west-flash="--runner pyocd"
```

### Anatomy of a Test

Every test needs a `testcase.yaml` in its root. Here's a real example from `tests/kernel/threads/lifecycle`:

```yaml
# testcase.yaml
tests:
  kernel.threads.lifecycle:
    # Human-readable description
    description: Test thread creation, suspension, and termination
    
    # Tags for filtering (e.g., twister -t kernel)
    tags: kernel threads
    
    # Platform filters: only run on these
    platform_allow: qemu_cortex_m3 native_posix
    
    # Integration test (longer runtime, not in sanitycheck)
    integration_platforms:
      - qemu_cortex_m3
    
    # Timeout in seconds (default 60)
    timeout: 120
    
    # Test type: 'unit' (no hardware needed) or 'integration'
    type: unit
```

The test application itself must print `PROJECT EXECUTION SUCCESSFUL` to stdout on completion. Twister greps for this string to determine pass/fail.

### Filtering Tests

Twister's real power is selective execution:

```bash
# Run only kernel tests
twister -p qemu_cortex_m3 -T tests/kernel -v

# Run tests tagged "bluetooth" on all supported platforms
twister -t bluetooth -v

# Run tests that require a specific Kconfig
twister -p qemu_cortex_m3 -T tests/ -v \
  --extra-args=CONFIG_SYS_CLOCK_TICKS_PER_SEC=100

# Exclude slow tests
twister -p qemu_cortex_m3 -T tests/ -v --exclude-tag="slow"
```

### Test Results

Twister outputs a comprehensive report:

```bash
# After run, results are in twister-out/
ls twister-out/
# twister.log        # Full log
# testplan.json      # What was planned to run
# testresults.json   # Pass/fail per test
# reports/           # HTML and JUnit XML reports

# View summary
cat twister-out/twister.log | tail -20
# INFO    - Total test cases: 142
# INFO    - PASS: 138
# INFO    - FAIL: 2
# INFO    - SKIP: 2 (due to platform filter)
```

## Common Pitfalls & Gotchas

### 1. Missing `PROJECT EXECUTION SUCCESSFUL`

Twister doesn't parse your test logic—it just looks for that exact string on stdout. If your test passes but prints something else (like a custom "TEST PASSED" message), Twister will report it as failed. Always end your test with:

```c
printk("PROJECT EXECUTION SUCCESSFUL\n");
```

### 2. Platform Mismatch in `platform_allow`

A common mistake is listing a platform that doesn't exist or has a different name than what Twister expects. Use `twister --list-platforms` to see valid names. For example, `nrf52840dk_nrf52840` is correct, but `nrf52840dk` is not.

### 3. Timeout on Real Hardware

When testing on actual boards, the default 60-second timeout often isn't enough for tests that wait for external events (e.g., Bluetooth pairing). Always set a generous `timeout` in `testcase.yaml`, and use `--device-serial-pty` to see live output during debugging:

```bash
twister -p nrf52840dk_nrf52840 -T tests/bluetooth -v \
  --device-testing --device-serial-pty
```

### 4. Forgetting to Clean Build Artifacts

Twister caches builds. If you change a test source but not its configuration, Twister might reuse a stale binary. Use `--clean` to force a rebuild:

```bash
twister -p qemu_cortex_m3 -T tests/kernel -v --clean
```

## Try It Yourself

1. **Run your first Twister suite**: Navigate to your Zephyr tree and run `twister -p qemu_cortex_m3 -T tests/kernel/sched/ -v`. Observe the output—note which tests pass, fail, or are skipped.

2. **Write a minimal test**: Create a new directory `tests/my_first_test/` with a `testcase.yaml` and a `src/main.c` that prints `PROJECT EXECUTION SUCCESSFUL`. Run it with `twister -p qemu_cortex_m3 -T tests/my_first_test/`.

3. **Test on real hardware**: If you have a supported board, run `twister -p <your_board> -T tests/kernel/threads/lifecycle/ --device-testing --device-serial /dev/ttyACM0`. Add `--west-flash="--runner <your_runner>"` (e.g., `pyocd`, `jlink`, `openocd`).

## Next Up

Tomorrow, we move from automated testing to interactive debugging: **GDB + OpenOCD: JTAG Debug on Real Hardware**. We'll set up a JTAG probe, connect GDB to a running Zephyr target, and step through code with hardware breakpoints and memory inspection.
