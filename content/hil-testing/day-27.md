---
title: "Day 27: Serial Console Automation: pexpect & miniterm"
date: 2026-07-09
tags: ["til", "hil-testing", "serial", "automation"]
---

## What I Explored Today

Today I tackled a pain point that's been nagging me for weeks: automating interactions with a device's serial console during HIL tests. Manual `screen` or `minicom` sessions are fine for debugging, but they're useless in CI. I spent the day building a reliable serial automation layer using Python's `pexpect` for scripted interactions and `miniterm` for interactive debugging. The result is a reusable harness that can flash firmware, parse boot logs, and run shell commands on the DUT—all from a Jenkins pipeline.

## The Core Concept

Serial consoles are the lowest common denominator for embedded device interaction. Before networking stacks are up, before USB gadgets enumerate, there's UART—typically 115200 baud, 8N1, no flow control. In HIL, we need to treat the serial port as a test interface, not just a debug port.

The key insight: **serial automation is about pattern matching on time-series text**. You're not just sending commands; you're waiting for specific prompts, log lines, or error messages to appear within timeouts. This is fundamentally different from network-based automation (SSH, REST) where you get structured responses. Serial is a firehose of unstructured text, and your automation must be robust to noise, partial lines, and timing jitter.

`pexpect` handles this by spawning a child process (like `screen` or a raw serial connection) and waiting for regex patterns. `miniterm` (from `pyserial`) is the complementary tool for manual debugging—it gives you a clean terminal with logging, timestamping, and script injection.

## Key Commands / Configuration / Code

### 1. Setting up the serial connection with pyserial + pexpect

```python
import pexpect
import serial
import time

# Don't use pexpect.spawn('screen /dev/ttyUSB0 115200')
# Instead, use a raw serial wrapper for better control
class SerialSpawn:
    """Wraps pyserial Serial object for pexpect compatibility."""
    def __init__(self, port, baud=115200, timeout=10):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self.buffer = b''
        self.timeout = timeout

    def read(self, size=1):
        return self.ser.read(size)

    def write(self, data):
        self.ser.write(data)

    def flush(self):
        self.ser.flush()

    def close(self):
        self.ser.close()

# Usage in a test
spawn = SerialSpawn('/dev/ttyUSB0', baud=115200, timeout=30)
child = pexpect.spawn('cat', timeout=30)  # dummy spawn, we'll override
child.child_fd = spawn.ser.fileno()  # attach our serial fd
```

**Better approach**: Use `pexpect.fdpexpect.fdspawn` for file descriptor-based control:

```python
import pexpect.fdpexpect
import serial

ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=10)
child = pexpect.fdpexpect.fdspawn(ser.fileno(), timeout=30)

# Wait for bootloader prompt
child.expect('U-Boot>', timeout=5)

# Send a command
child.sendline('printenv')
child.expect('U-Boot>', timeout=10)
print(child.before.decode())  # Capture environment variables
```

### 2. Automating a firmware flash sequence

```python
def flash_via_serial(port, firmware_path):
    """Flash firmware via serial bootloader (e.g., U-Boot)."""
    ser = serial.Serial(port, 115200, timeout=10)
    child = pexpect.fdpexpect.fdspawn(ser.fileno(), timeout=30)

    # Reset DUT (assumes DTR triggers reset)
    ser.setDTR(False)
    time.sleep(0.1)
    ser.setDTR(True)
    time.sleep(0.5)

    # Wait for boot prompt
    index = child.expect(['U-Boot>', 'Hit any key to stop autoboot'], timeout=10)
    if index == 1:
        child.sendline('')  # Interrupt autoboot
        child.expect('U-Boot>', timeout=5)

    # Send flash command (example: Ymodem transfer)
    child.sendline('loady')
    child.expect('C', timeout=5)  # Ymodem ready character

    # Use lrzsz for file transfer
    import subprocess
    subprocess.run(['sz', '-Y', '--ymodem', firmware_path],
                   stdin=ser, stdout=ser, timeout=60)

    child.expect('U-Boot>', timeout=120)
    child.sendline('boot')
    return child.expect('login:', timeout=60)
```

### 3. Interactive debugging with miniterm

```bash
# Install pyserial for miniterm
pip install pyserial

# Basic usage with logging
python -m serial.tools.miniterm /dev/ttyUSB0 115200 \
    --logfile serial_log_$(date +%Y%m%d_%H%M%S).txt \
    --timestamp

# Filter out specific patterns (e.g., kernel messages)
# In miniterm, press Ctrl+T, Ctrl+L to toggle logging
# Press Ctrl+T, Ctrl+E to echo local input
```

### 4. CI-friendly serial test pattern

```python
def test_boot_complete():
    """Verify DUT boots to Linux shell."""
    with serial.Serial('/dev/ttyUSB0', 115200, timeout=10) as ser:
        child = pexpect.fdpexpect.fdspawn(ser.fileno(), timeout=60)

        # Reset and wait for kernel panic or login prompt
        ser.setDTR(False)
        time.sleep(0.2)
        ser.setDTR(True)

        result = child.expect([
            'login:',           # Successful boot
            'Kernel panic',     # Boot failure
            'Kernel Oops',      # Kernel error
            pexpect.TIMEOUT     # No response
        ])

        assert result == 0, f"Boot failed, got: {child.before.decode()}"
        print("Boot successful, login prompt detected")
```

## Common Pitfalls & Gotchas

1. **Baud rate mismatch on partial boot**: Some bootloaders run at a different baud rate than the kernel. I've seen U-Boot at 115200 and Linux switch to 57600. Always check the boot log for baud rate changes, or configure the kernel to keep the bootloader's rate.

2. **Buffer overflow with fast output**: When the DUT spews boot logs at high speed, `pexpect` can miss patterns if the OS buffer fills. Solution: increase the serial buffer size (`sysctl -w net.core.rmem_default=262144` doesn't apply—use `serial.Serial(..., rtscts=True)` or increase the read buffer in pyserial: `ser.set_buffer_size(rx_size=65536)`).

3. **DTR/RTS line conflicts**: Many USB-serial adapters use DTR for reset and RTS for boot mode selection. If your automation toggles DTR, ensure no other process (like `systemd`'s serial-getty) is also controlling those lines. Use `lsof /dev/ttyUSB0` to check for competing processes.

## Try It Yourself

1. **Capture boot logs programmatically**: Write a Python script that connects to your DUT's serial port, resets the device, and captures all output until a login prompt appears. Save the log to a file with timestamps.

2. **Build a command-response test**: Automate sending `uname -a`, `cat /proc/cpuinfo`, and `free -h` to the DUT's serial console. Parse the responses and assert that the kernel version matches your expected build.

3. **Implement a watchdog reset test**: Write a test that sends a command to crash the DUT (e.g., `echo c > /proc/sysrq-trigger`), waits for the serial console to show a reboot, and measures the time from crash to login prompt. Assert it's under 30 seconds.

## Next Up: GPIO Control from Host: Controlling DUT via Relay

Tomorrow, I'm moving from passive serial monitoring to active hardware control. We'll wire up a USB-controlled relay board to physically power-cycle the DUT, toggle boot mode pins, and simulate fault conditions—all from Python. This is the missing piece for fully automated HIL reset and recovery testing.
