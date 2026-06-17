---
title: "Day 05: pytest-embedded: Python Test Runner for Embedded"
date: 2026-06-17
tags: ["til", "hil-testing", "pytest", "embedded", "python"]
---

## What I Explored Today

Today I integrated `pytest-embedded` into our HIL pipeline for an ESP32-S3 target running FreeRTOS. This plugin extends standard pytest with fixtures and hooks specifically designed for embedded workflows—serial port interaction, flash/erase cycles, DUT reset, and log parsing. After fighting with raw `pyserial` scripts for weeks, this feels like a proper testing framework rather than a collection of ad-hoc Python scripts.

## The Core Concept

The fundamental problem with embedded testing is that your "test runner" and your "system under test" are physically separate machines. Standard pytest assumes everything runs in the same process. `pytest-embedded` bridges this gap by providing fixtures that manage the hardware lifecycle: connect to the DUT via serial/JTAG, flash firmware, reset, capture output, and clean up—all within pytest's fixture scope and teardown model.

Why not just use `unittest` with `pyserial`? Because you lose test isolation, fixture reuse, parameterization, and reporting. `pytest-embedded` gives you:

- **Automatic DUT management**: Each test function gets a clean hardware state (if you configure it that way)
- **Structured log parsing**: Regex-based pattern matching on serial output, not fragile string searches
- **Parallel execution**: Run tests across multiple boards simultaneously using `pytest-xdist`
- **CI integration**: JUnit XML output, coverage reports, and artifact collection out of the box

The key insight is that embedded tests are integration tests—they verify that your firmware interacts correctly with real hardware. `pytest-embedded` treats the DUT as a test fixture, not a black box you manually control.

## Key Commands / Configuration / Code

### Installation
```bash
pip install pytest-embedded
# For ESP32-specific features (JTAG, IDF integration):
pip install pytest-embedded-esp
```

### Basic Test Structure
```python
# test_blink.py
import pytest

def test_led_toggle(dut):
    """Verify LED toggles at 1 Hz after boot."""
    # dut is a fixture that connects to the DUT via serial
    # It automatically flashes firmware if configured
    
    # Wait for boot message
    dut.expect("FreeRTOS started", timeout=10)
    
    # Capture 3 LED toggle cycles
    for _ in range(3):
        dut.expect("LED ON", timeout=2)
        dut.expect("LED OFF", timeout=2)
    
    # Verify timing (pytest-embedded captures timestamps)
    timestamps = [match.timestamp for match in dut.expect(
        r"(LED ON|LED OFF)", timeout=10, count=6
    )]
    intervals = [timestamps[i+1] - timestamps[i] for i in range(0, len(timestamps), 2)]
    assert all(0.9 < t < 1.1 for t in intervals), f"Timing off: {intervals}"
```

### Configuration via `pytest.ini`
```ini
[pytest]
# Default serial port and baud rate
embedded_serial_ports = /dev/ttyUSB0
embedded_serial_baud = 115200

# App binary to flash before tests
embedded_app_path = build/test_app.bin

# Timeout for all expect calls (seconds)
embedded_expect_timeout = 30

# Log all serial output to file
embedded_log_file = serial_output.log
```

### Advanced: Parameterized Multi-Board Testing
```python
# conftest.py
import pytest

def pytest_addoption(parser):
    parser.addoption("--board", action="store", default="esp32s3",
                     help="Target board variant")

@pytest.fixture
def dut_config(request):
    board = request.config.getoption("--board")
    configs = {
        "esp32s3": {
            "port": "/dev/ttyUSB0",
            "baud": 115200,
            "app": f"build/{board}/test_app.bin"
        },
        "esp32c3": {
            "port": "/dev/ttyUSB1",
            "baud": 921600,
            "app": f"build/{board}/test_app.bin"
        }
    }
    return configs[board]

# test_sensor.py
import pytest

@pytest.mark.parametrize("sensor_id", [0, 1, 2])
def test_i2c_sensor_read(dut, sensor_id):
    """Read temperature from each I2C sensor."""
    dut.write(f"read_sensor {sensor_id}\n")
    result = dut.expect(r"Temperature: (\d+\.\d+) C", timeout=5)
    temp = float(result.group(1))
    assert 15.0 <= temp <= 35.0, f"Sensor {sensor_id}: {temp}°C out of range"
```

### Running Tests
```bash
# Basic run
pytest --embedded-services esp,serial

# With verbose output and logging
pytest -v --embedded-services esp,serial --log-cli-level=DEBUG

# Run on specific board
pytest --board esp32c3 --embedded-services esp,serial

# Generate JUnit report for CI
pytest --junitxml=results.xml --embedded-services esp,serial
```

## Common Pitfalls & Gotchas

1. **Serial port contention**: If your DUT resets during flashing, the serial port may be briefly unavailable. Always use `dut.expect()` with generous timeouts (10-30s) after flash operations. Also, ensure no other process (like `minicom` or `idf.py monitor`) holds the port open.

2. **Fixture scope confusion**: By default, `dut` is function-scoped—a new flash happens for every test. This is safe but slow. For integration tests where state doesn't matter, use `scope="module"` in your fixture to flash once per module. But beware: if a test crashes the DUT, subsequent tests will fail silently.

3. **Regex anchoring**: `dut.expect()` uses `re.search()`, not `re.match()`. If you need to match at the start of a line, use `r"^LED ON"` with `multiline=True` flag. Otherwise, partial matches in the middle of a long serial line will pass unexpectedly.

## Try It Yourself

1. **Write a boot-time test**: Create a test that connects to your DUT, waits for the boot banner, and verifies the firmware version string matches an expected pattern. Use `dut.expect(r"Version: (\d+\.\d+\.\d+)")`.

2. **Implement a command-response test**: Add a custom CLI command to your firmware (e.g., `stats` that prints memory usage). Write a pytest that sends `stats\n` via `dut.write()`, captures the output, and asserts free heap is above 50%.

3. **Multi-board stress test**: If you have two boards, parameterize your tests to run the same I2C sensor read test on both. Use `pytest-xdist` with `-n 2` to run them in parallel. Measure the total execution time vs sequential.

## Next Up

Tomorrow, I'm diving into **Twister: Zephyr CI Test Runner for Multiple Boards**. Twister is Zephyr's built-in test framework that handles cross-compilation, flashing, and test execution across dozens of board configurations. I'll compare it with pytest-embedded and show how to integrate both into a unified CI pipeline.
