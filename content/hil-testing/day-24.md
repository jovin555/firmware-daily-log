---
title: "Day 24: pytest-embedded: Python Test Runner for Embedded"
date: 2026-07-06
tags: ["til", "hil-testing", "pytest", "embedded", "python"]
---

## What I Explored Today

Today I integrated `pytest-embedded` into our HIL workflow for an ESP32-S3 target running FreeRTOS. This plugin extends standard pytest with fixtures for serial, JTAG, and QEMU backends, letting me write Python test cases that interact with real hardware or simulators. After fighting with ad-hoc shell scripts for months, having a structured, parameterized test runner feels like a genuine upgrade.

## The Core Concept

The fundamental problem with embedded testing is the impedance mismatch between host-side test frameworks and target-side execution. Traditional unit tests run on the host, mocking hardware—useful but insufficient for integration or HIL. `pytest-embedded` solves this by providing a Pythonic bridge: your test script runs on the host, but it can flash firmware, open a serial connection, send commands, and assert on target output—all within a single pytest session.

Why not just use `pexpect` or `pySerial` directly? Because `pytest-embedded` gives you:
- **Fixtures** that handle board setup/teardown (flash, reset, serial open/close)
- **Logging** with timestamps and automatic log file capture
- **Parallelism** via `pytest-xdist` for multi-DUT setups
- **App management** to compile and flash from within the test

The architecture is plugin-based: `pytest-embedded-serial` for UART, `pytest-embedded-jtag` for OpenOCD/GDB, `pytest-embedded-qemu` for simulation. You mix and match backends per test or per session.

## Key Commands / Configuration / Code

### Installation
```bash
pip install pytest-embedded pytest-embedded-serial pytest-embedded-qemu
```

### Minimal test: serial echo
```python
# test_echo.py
import pytest

def test_serial_echo(dut):
    """
    Flash firmware, open serial, send 'hello', expect 'hello' back.
    """
    # 'dut' is a fixture that handles flash + serial connection
    dut.write('hello\n')
    output = dut.read()
    assert 'hello' in output, f"Expected 'hello', got: {output}"
```

Run with:
```bash
pytest --embedded-services serial --port /dev/ttyUSB0 test_echo.py
```

### Parameterized test across multiple boards
```python
# test_multi_board.py
import pytest

@pytest.mark.parametrize("target", ["esp32", "esp32s3"])
def test_blink_led(dut, target):
    """
    Test that LED toggles at 1 Hz. Target-specific flash config.
    """
    # 'dut' auto-detects target from config or fixture override
    dut.write('led on\n')
    # Read serial output for 2 seconds
    output = dut.read(2.0)
    assert 'LED ON' in output
```

Run with target-specific config:
```bash
pytest --embedded-services serial --app-path ./build_esp32 --port /dev/ttyUSB0 \
       --target esp32 test_multi_board.py
```

### Custom fixture with QEMU backend
```python
# conftest.py
import pytest

@pytest.fixture(scope='module')
def qemu_dut(request):
    """Start QEMU with a prebuilt image, yield DUT, then kill QEMU."""
    from pytest_embedded_qemu import Qemu
    qemu = Qemu(
        binary='./build/zephyr/zephyr.elf',
        machine='mps2-an385',
        serial='stdio'
    )
    qemu.start()
    yield qemu
    qemu.stop()
```

Test using it:
```python
def test_qemu_hello(qemu_dut):
    qemu_dut.write('help\n')
    output = qemu_dut.read(timeout=5)
    assert 'Available commands' in output
```

### Logging and artifacts
```python
# Automatically captured by pytest-embedded
# Logs go to: ./logs/test_name_<timestamp>.log
# You can also attach custom artifacts:
def test_capture_log(dut):
    dut.write('run test\n')
    # Access the serial log as a string
    full_log = dut.serial.log
    assert 'PASS' in full_log
```

## Common Pitfalls & Gotchas

1. **Serial port contention** – If your test crashes or you Ctrl+C, the serial port may stay locked. Always use `--embedded-services serial --port <port>` with explicit teardown. I add a `pytest-timeout` plugin to force-kill hung tests: `pip install pytest-timeout` and run with `--timeout 60`.

2. **Flashing without confirmation** – By default, `pytest-embedded` flashes the target before each test. This is slow for iterative debugging. Use `--skip-flash` if you flashed manually, or set `--reflash False` in your pytest config. I keep a `pytest.ini` with:
   ```ini
   [pytest]
   addopts = --embedded-services serial --reflash False
   ```

3. **Timing assumptions** – `dut.read(timeout=1.0)` blocks for exactly 1 second. If your target outputs data after 1.1 seconds, the test fails. Always add margin, and prefer `dut.expect(pattern, timeout=...)` which returns as soon as the pattern matches, rather than fixed-duration reads.

4. **Fixture scope confusion** – The `dut` fixture is function-scoped by default. For multi-test sessions on the same board, change scope to `module` in `conftest.py`:
   ```python
   @pytest.fixture(scope='module')
   def dut(request):
       ...
   ```

## Try It Yourself

1. **Basic serial echo test** – Flash a simple firmware that echoes UART input (e.g., ESP-IDF `echo` example). Write a pytest that sends "ping" and asserts "pong" is received. Run with `--embedded-services serial --port /dev/ttyUSB0`.

2. **Multi-board parameterization** – Set up two different boards (e.g., ESP32 and nRF52840). Write a parameterized test that flashes each, sends a unique command, and verifies board-specific output. Use `pytest.ini` to set default ports per target.

3. **QEMU integration test** – Build a Zephyr sample (e.g., `samples/synchronization`) for the `mps2-an385` target. Write a pytest that boots it in QEMU, waits for "threads started", and captures the output log as an artifact. Run with `--embedded-services qemu`.

## Next Up

Tomorrow I’ll tackle **Twister: Zephyr CI Test Runner for Multiple Boards** – how to define test scenarios, run across real and simulated targets in parallel, and integrate with CI pipelines. Twister handles board-specific configurations, test filtering, and result reporting, making it the go-to for Zephyr-based projects.
