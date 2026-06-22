---
title: "Day 08: Serial Console Automation: pexpect & miniterm"
date: 2026-06-22
tags: ["til", "hil-testing", "serial", "automation"]
---

## What I Explored Today

Today I dug into automating serial console interactions for HIL testing. While manual `screen` or `minicom` sessions work for debugging, they're useless for CI. I needed a way to send commands to a DUT (Device Under Test) over UART, wait for specific prompts, and assert the output—all from Python. I explored two complementary tools: `pexpect` for scripted automation and `miniterm` (from `pyserial`) for interactive debugging and log capture. The goal: replace manual "type command, read output" workflows with deterministic, testable automation.

## The Core Concept

Serial consoles are the lowest common denominator for embedded systems. Before networking, before JTAG, you have a UART. In HIL, we use it for boot log capture, shell interaction, and even firmware flashing. But serial is inherently asynchronous and line-oriented—you send bytes, you receive bytes, and there's no built-in handshake for "command complete."

The key insight: **automating serial means pattern-matching on output, not timing**. You can't just `sleep(2)` and hope. You need to wait for a specific prompt (e.g., `root@board:~#`) before sending the next command. `pexpect` does exactly this: it spawns a serial connection, sends commands, and waits for expected patterns with timeouts. `miniterm` is its manual counterpart—a terminal emulator that logs everything to a file, which is invaluable for debugging test failures.

Together, they form the backbone of non-interactive DUT control. Once you automate serial, you can script boot tests, flash verification, and even reboot loops—all from a CI pipeline.

## Key Commands / Configuration / Code

### 1. Setting up the serial port with pyserial

First, install `pyserial` and `pexpect`:

```bash
pip install pyserial pexpect
```

Identify your serial port (usually `/dev/ttyUSB0` or `/dev/ttyACM0` on Linux):

```bash
ls -l /dev/ttyUSB*
# or
dmesg | grep tty
```

### 2. Interactive debugging with miniterm

`miniterm` ships with `pyserial`. Use it to verify your connection and capture raw output:

```bash
# Basic usage (115200 baud, 8N1)
python -m serial.tools.miniterm /dev/ttyUSB0 115200

# With timestamped log file
python -m serial.tools.miniterm /dev/ttyUSB0 115200 --logfile serial_log.txt

# Exit: Ctrl+]
```

Pro tip: Always run `miniterm` first to confirm baud rate and line endings. A common mistake is assuming `\n` when the DUT expects `\r\n`.

### 3. Scripted automation with pexpect

Here's a real HIL test script that boots a board, logs in, runs a command, and asserts the output:

```python
#!/usr/bin/env python3
import pexpect
import sys
import time

SERIAL_PORT = "/dev/ttyUSB0"
BAUD = 115200
TIMEOUT = 30  # seconds, adjust for slow boot

def test_boot_and_uptime():
    """Connect to DUT, wait for login prompt, check uptime."""
    child = pexpect.spawn(
        f"python -m serial.tools.miniterm {SERIAL_PORT} {BAUD}",
        timeout=TIMEOUT,
        encoding='utf-8',
        codec_errors='replace'
    )

    # Wait for boot to complete and login prompt
    # Common patterns: 'login:', 'root@board:~#', 'Press Enter to activate console'
    index = child.expect([
        'login:',
        'root@.*#',
        'Press Enter',
        pexpect.TIMEOUT
    ])

    if index == 0:
        # Login prompt: send credentials
        child.sendline('root')
        child.expect('Password:')
        child.sendline('')  # often no password
        child.expect('root@.*#')
    elif index == 1:
        # Already at shell prompt
        pass
    elif index == 2:
        # Press Enter to activate
        child.sendline('')
        child.expect('root@.*#')
    else:
        print("ERROR: Boot timeout")
        child.close()
        sys.exit(1)

    # Now we're at the shell. Run a command.
    child.sendline('uptime')
    child.expect(r'up\s+\d+\s+\w+.*')  # match "up X min" or "up X days"
    output = child.before + child.after
    print(f"Uptime output: {output}")

    # Assert the board has been running for at least 1 minute
    assert 'up' in output, f"Uptime check failed: {output}"

    # Clean exit
    child.sendline('exit')
    child.close()
    print("PASS: Boot and uptime test passed")

if __name__ == "__main__":
    test_boot_and_uptime()
```

### 4. Handling multiple commands with a helper function

For longer test sequences, wrap the pattern matching:

```python
def send_cmd(child, cmd, expected_prompt='root@.*#', timeout=10):
    """Send a command and wait for the shell prompt to return."""
    child.sendline(cmd)
    child.expect(expected_prompt, timeout=timeout)
    # child.before contains the command output (excluding the prompt)
    return child.before

# Usage:
output = send_cmd(child, 'cat /proc/cpuinfo')
assert 'ARM' in output, "Not an ARM processor!"
```

## Common Pitfalls & Gotchas

1. **Line ending mismatch.** Many embedded UARTs expect `\r\n` (CR+LF), but pexpect's `sendline()` sends `\n` by default. Fix: use `child.sendline(cmd + '\r')` or configure the DUT's shell to accept `\n`. Always check with `miniterm` first.

2. **Buffer overflow on slow boards.** If you send commands too fast, the DUT's UART buffer may drop characters. Insert a small `time.sleep(0.1)` between sends, or use `pexpect`'s `delaybeforesend` parameter: `child = pexpect.spawn(..., delaybeforesend=0.05)`.

3. **Expecting too much, too soon.** Don't expect the exact prompt string. Use regex patterns like `root@.*#` or `\$\s*$` to match variable hostnames or paths. Also, always handle `pexpect.TIMEOUT` and `pexpect.EOF`—a crashed board shouldn't hang your test suite.

## Try It Yourself

1. **Capture a boot log.** Use `miniterm` with `--logfile` to record the full boot sequence of your DUT. Then write a pexpect script that parses the log for "Kernel panic" or "Oops" and fails the test if found.

2. **Automate a firmware version check.** Write a script that logs into the DUT, runs `cat /etc/version` (or equivalent), and asserts the version string matches an expected pattern. Run it as a CI step.

3. **Stress test the serial link.** Create a loop that sends `echo "hello"` 100 times, each time waiting for the prompt. Measure the average response time. If any iteration times out, flag it as a serial reliability issue.

## Next Up

Tomorrow: **GPIO Control from Host: Controlling DUT via Relay**. We'll wire a USB GPIO controller to the DUT's power relay, enabling hard power-cycles and fault injection—all from Python. No more manual reset button presses.
