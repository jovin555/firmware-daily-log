---
title: "Day 26: OpenOCD & pyOCD: Programmatic Flash & Debug"
date: 2026-07-08
tags: ["til", "hil-testing", "openocd", "pyocd", "flashing"]
---

## What I Explored Today

Today I dove deep into the two dominant open-source tools for programmatic flash and debug in embedded HIL environments: OpenOCD and pyOCD. While both serve the same fundamental purpose—connecting to a target microcontroller via a debug probe (JTAG/SWD) to program and control execution—they differ significantly in architecture, scripting capabilities, and integration patterns. I spent the morning building reproducible flash pipelines with OpenOCD's TCL scripting engine, then switched to pyOCD's Python API for more dynamic test orchestration. The key insight: OpenOCD excels at hardware-near operations with minimal dependencies, while pyOCD shines when you need to embed debug control directly into Python-based test frameworks.

## The Core Concept

The fundamental problem these tools solve is moving beyond "click a button in an IDE" to "flash and debug from a script." In HIL testing, you need to:

1. **Flash firmware** reliably across dozens of boards in parallel
2. **Reset and halt** the target at a known state before each test
3. **Read/write memory and registers** to inject test vectors or verify state
4. **Set breakpoints and watchpoints** for fault injection or coverage analysis

Both OpenOCD and pyOCD speak the same low-level protocols (SWD/JTAG) via a debug probe (ST-Link, J-Link, CMSIS-DAP), but they expose different interfaces. OpenOCD runs as a daemon with a TCL command interface, making it ideal for shell scripts and Makefiles. pyOCD is a Python library that gives you direct object-level control over the target—perfect for integrating with pytest, unittest, or custom HIL orchestrators.

## Key Commands / Configuration / Code

### OpenOCD: The Workhorse

Basic flash and reset sequence via command line:

```bash
# Flash firmware and immediately halt at reset vector
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
  -c "program build/firmware.elf verify reset exit"

# Interactive session for debugging
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg
# In another terminal:
telnet localhost 4444
> halt
> mdw 0x08000000 16    # read 16 words from flash base
> mww 0x20000000 0xDEADBEEF  # write to SRAM
> resume
```

For automated HIL, I use a wrapper script:

```bash
#!/bin/bash
# flash_and_test.sh - Flash, run, capture output
set -euo pipefail

openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
  -c "program build/firmware.elf verify reset exit" \
  -l /dev/null 2>&1 | grep -v "Info :"

# Wait for target to boot and start UART output
sleep 2
python3 -c "
import serial
with serial.Serial('/dev/ttyACM0', 115200, timeout=5) as ser:
    print(ser.read(1024).decode())
"
```

### pyOCD: Python-First Control

Install with `pip install pyocd`, then use the Python API:

```python
# flash_and_debug.py
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
import time

def flash_and_verify(hex_path: str, probe_id: str = None) -> dict:
    """Flash firmware and verify checksum, return target info."""
    with ConnectHelper.session_with_chip(
        probe_id=probe_id,
        target_override="stm32f407vg"
    ) as session:
        board = session.board
        target = board.target

        # Halt target before flash
        target.halt()
        print(f"Target halted: {target.read_core_register('pc'):#010x}")

        # Program flash with verification
        programmer = FileProgrammer(session)
        programmer.program(hex_path, file_format="hex", auto_erase=True)

        # Verify by reading back and comparing CRC
        crc = target.compute_crc(0x08000000, 0x10000)  # 64KB region
        print(f"Flash CRC32: {crc:#010x}")

        # Reset and run
        target.reset_and_halt()
        target.resume()

        return {
            "crc": crc,
            "pc_after_reset": target.read_core_register("pc"),
        }

if __name__ == "__main__":
    result = flash_and_verify("build/firmware.hex")
    assert result["crc"] != 0, "Flash verification failed!"
```

For parallel flashing across multiple probes:

```python
from concurrent.futures import ThreadPoolExecutor
from pyocd.core.helpers import ConnectHelper

def flash_board(probe_id: str, hex_path: str):
    """Flash a single board by probe serial number."""
    with ConnectHelper.session_with_chip(probe_id=probe_id) as session:
        board = session.board
        board.target.halt()
        FileProgrammer(session).program(hex_path)
        board.target.reset_and_halt()
    return f"Board {probe_id} flashed OK"

# Flash 4 boards concurrently
probes = ["STLINK_001", "STLINK_002", "STLINK_003", "STLINK_004"]
with ThreadPoolExecutor(max_workers=4) as executor:
    results = executor.map(lambda pid: flash_board(pid, "firmware.hex"), probes)
    for r in results:
        print(r)
```

## Common Pitfalls & Gotchas

1. **OpenOCD config mismatch kills your day.** The `-f target/stm32f4x.cfg` is a generic config that assumes a 1MB flash STM32F4. If your chip is an STM32F401 (512KB flash), the flash algorithm will fail silently or brick the target. Always verify with `flash banks` after connecting, or use a chip-specific config like `target/stm32f4x_stlink.cfg`.

2. **pyOCD probe discovery timeout.** When using `ConnectHelper.session_with_chip()` without a `probe_id`, pyOCD scans all USB devices. If you have multiple probes, this can take 10+ seconds and may pick the wrong one. Always pass the probe's unique serial number (get it from `pyocd list`). In CI, store serials in a JSON config file.

3. **Reset vs. reset_and_halt confusion.** OpenOCD's `reset` does a full system reset and runs. `reset halt` halts at reset vector. pyOCD's `target.reset_and_halt()` is the safe default for HIL—it ensures the target is stopped before you try to set breakpoints or read registers. Using `target.reset()` alone in a script often leads to race conditions where the target runs past your breakpoint before you can set it.

## Try It Yourself

1. **Parallel flash stress test:** Write a Python script using pyOCD that flashes the same firmware to 3 different boards simultaneously. Measure total time vs. sequential flashing. Add a CRC verification step after each flash.

2. **OpenOCD GDB bridge:** Start OpenOCD in the background, then connect `arm-none-eabi-gdb` to port 3333. Write a GDB script that sets a hardware breakpoint on `main()`, runs the target, reads the stack pointer, and logs it to a file. Automate the whole sequence from a shell script.

3. **Fault injection with pyOCD:** Write a test that flashes firmware, then uses pyOCD to corrupt a specific RAM location (e.g., a CRC buffer) before resuming. Verify that the firmware's error handler triggers by monitoring a GPIO pin or UART output.

## Next Up

Tomorrow: **Serial Console Automation: pexpect & miniterm** — we'll move from flashing to interacting, automating UART-based test sequences with expect-like patterns and handling the quirks of serial consoles in CI pipelines.
