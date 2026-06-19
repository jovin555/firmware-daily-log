---
title: "Day 07: OpenOCD & pyOCD: Programmatic Flash & Debug"
date: 2026-06-19
tags: ["til", "hil-testing", "openocd", "pyocd", "flashing"]
---

## What I Explored Today

Today I dug into the two dominant open-source tools for programmatic flash and debug in embedded HIL environments: OpenOCD and pyOCD. While both serve the same fundamental purpose—talking to debug probes over JTAG/SWD to program and debug microcontrollers—they differ significantly in architecture, scripting capabilities, and integration patterns. I spent the day building reproducible flash pipelines for both, testing edge cases like power-cycling targets mid-flash, and validating that our CI runners can reliably recover from probe disconnections.

## The Core Concept

In a HIL test rig, you cannot rely on manual button-pressing or IDE-based flashing. Every board reset, firmware update, and debug session must be scripted and repeatable. OpenOCD and pyOCD are the two dominant solutions for this, but they approach the problem differently:

- **OpenOCD** is a C-based daemon that exposes a telnet/GDB interface and a TCL scripting engine. It's the old guard—rock solid, supports hundreds of targets and probes, but its configuration syntax is arcane and error-prone.
- **pyOCD** is a Python-native library and CLI tool. It's newer, more maintainable, and integrates naturally with Python-based test frameworks (pytest, unittest). It supports CMSIS-DAP probes natively and has a cleaner API.

The key insight: choose OpenOCD when you need maximum hardware compatibility (e.g., legacy JTAG adapters) or when your team already has TCL-based scripts. Choose pyOCD when you want Python-native control, better error handling, and easier CI integration.

## Key Commands / Configuration / Code

### OpenOCD: Basic Flash & Debug Session

```bash
# Start OpenOCD with a ST-Link/V2 probe and STM32F4 target
# Config file combines interface and target settings
openocd -f interface/stlink-v2.cfg -f target/stm32f4x.cfg

# In another terminal, connect via telnet for interactive control
telnet localhost 4444

# Inside telnet session:
# halt the CPU, erase, program, verify, then reset
> halt
> flash write_image erase /path/to/firmware.hex
> verify_image /path/to/firmware.hex
> reset run
> exit
```

For CI automation, use a scripted approach:

```bash
# One-shot flash with OpenOCD (no interactive telnet needed)
openocd -f interface/stlink-v2.cfg \
        -f target/stm32f4x.cfg \
        -c "init; halt; flash write_image erase firmware.hex; verify_image firmware.hex; reset run; exit"
```

### pyOCD: Python-Native Flash & Debug

```python
#!/usr/bin/env python3
"""Programmatic flash and debug with pyOCD"""
from pyocd.core.helpers import ConnectHelper
from pyocd.flash.file_programmer import FileProgrammer
import logging

logging.basicConfig(level=logging.INFO)

def flash_and_verify(hex_path: str, target_override: str = None):
    """
    Flash firmware and verify. Handles probe discovery and connection.
    """
    with ConnectHelper.session_with_chosen_probe(
        target_override=target_override,
        unique_id=None,  # Auto-detect first probe
        connect_mode='halt'  # Halt CPU before flash
    ) as session:
        board = session.board
        target = board.target
        
        # Halt and unlock flash (required for many MCUs)
        target.halt()
        target.set_target_state('PROGRAM')
        
        # Program the flash
        programmer = FileProgrammer(session)
        programmer.program(hex_path, file_format='hex', 
                          erase_mode='sector', trust_crc=False)
        
        # Verify by reading back and comparing CRC
        programmer.verify(hex_path, file_format='hex')
        
        # Reset and run
        target.reset_and_halt()
        target.resume()
        
        print(f"Flash successful: {hex_path}")

# Usage
flash_and_verify("build/firmware.hex", target_override="stm32f407vg")
```

### CI Integration Pattern (GitLab CI example)

```yaml
flash-job:
  stage: flash
  script:
    # Ensure probe is visible
    - lsusb | grep -i "st-link"
    # Flash with retry logic (probes sometimes glitch)
    - for i in 1 2 3; do
        pyocd flash -t stm32f407vg build/firmware.hex && break;
        echo "Flash attempt $i failed, retrying...";
        sleep 2;
      done
    # Verify the target is running
    - pyocd commander -t stm32f407vg -c "reset; sleep 100; read32 0x08000000 4"
  artifacts:
    paths:
      - flash_log.txt
```

## Common Pitfalls & Gotchas

1. **Power sequencing during flash**  
   Many debug probes (especially ST-Link clones) cannot supply enough current to power the target. If your board draws >300mA, use external power. OpenOCD will silently fail with cryptic "JTAG scan chain interrogation failed" errors. Always power the target separately and only connect SWD/JTAG lines.

2. **Flash protection bits left enabled**  
   Production MCUs often have RDP (Read Protection) level 1 or 2 set. OpenOCD and pyOCD will fail to erase or write. You must first issue a mass erase via `stm32_erase` in OpenOCD or `pyocd erase --mass` in pyOCD. This is a common CI failure when re-flashing previously deployed boards.

3. **OpenOCD TCL syntax is fragile**  
   A missing semicolon or incorrect whitespace in OpenOCD config files can cause silent failures. Always validate with `openocd -f your.cfg -c "exit"` before using in CI. pyOCD avoids this entirely with Python syntax checking.

## Try It Yourself

1. **Flash a firmware 10 times in a loop** using pyOCD's Python API. Add error handling that catches `pyocd.core.exceptions.TransferError` and retries with a power cycle (toggle a relay via GPIO) before giving up.

2. **Write an OpenOCD script** that dumps the first 1KB of flash to a file, then compares it against the original hex using `diff`. This validates that your flash pipeline is bit-exact.

3. **Set up a dual-probe test**: Use one probe (OpenOCD) to flash firmware, and a second probe (pyOCD) to read back memory addresses and verify the application is running (e.g., check a known magic value at a fixed RAM address).

## Next Up

Tomorrow we automate the serial console—no more manual `screen` sessions. I'll show how to use `pexpect` to interact with UART bootloaders and `miniterm` for logging, including how to handle line noise and unexpected resets in CI. **Serial Console Automation: pexpect & miniterm** is up next.
