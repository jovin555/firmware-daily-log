---
title: "Day 23: Penetration Testing Embedded Devices: Tools & Methodology"
date: 2026-07-23
tags: ["til", "threat-modeling", "pentest"]
---

## What I Explored Today

Today I moved from theoretical attack surface mapping into active exploitation — penetration testing embedded devices. Unlike web app pentesting, embedded testing requires physical access, specialized hardware, and a deep understanding of firmware, boot sequences, and hardware interfaces. I focused on the practical workflow: reconnaissance, firmware extraction, UART/serial discovery, and runtime analysis. The goal isn't just to find bugs, but to validate whether the attack surface we modeled actually yields exploitable entry points.

## The Core Concept

Penetration testing embedded devices is fundamentally different from testing a cloud API. You can't just send malformed JSON; you need to probe physical pins, sniff serial lines, and dump flash chips. The methodology follows a logical progression:

1. **Physical Reconnaissance** — Identify all external interfaces (JTAG, UART, SPI, I2C, USB, Ethernet, SD card slots). Document every chip, its markings, and datasheets.
2. **Firmware Extraction** — Dump firmware via SPI flash clips, JTAG/SWD, or bootloader exploits. Analyze the binary for hardcoded credentials, backdoors, and configuration files.
3. **Serial/UART Discovery** — Find UART pads, determine baud rate, and get a shell. This is often the fastest path to root.
4. **Runtime Analysis** — Monitor network traffic, probe debug interfaces, and test for common vulnerabilities (command injection, buffer overflows, insecure update mechanisms).

The key insight: embedded devices are often designed with "it works" as the only security requirement. Engineers leave debug UARTs populated, disable stack canaries for performance, and ship default credentials. Your job as a pentester is to find these shortcuts.

## Key Commands / Configuration / Code

### 1. UART Discovery with Logic Analyzer
Use a cheap logic analyzer (Saleae clone) to find UART TX/RX lines. Connect probes to suspect pads, then capture:

```bash
# Capture with sigrok/pulseview (CLI mode)
sigrok-cli -i uart_capture.sr -P uart:baudrate=115200,parity_type=none,stopbits=1 \
  -A uart:rx=1:tx=0 > uart_output.txt

# Or use Saleae Logic software with UART decoder
# Set threshold to 1.8V or 3.3V depending on device
```

### 2. Brute-Force UART Baud Rate
Many devices use non-standard baud rates. Use a Python script to iterate:

```python
# baud_brute.py — find UART baud rate automatically
import serial
import time

baud_rates = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
for baud in baud_rates:
    try:
        ser = serial.Serial('/dev/ttyUSB0', baud, timeout=1)
        ser.write(b'\n')  # Send newline to trigger boot output
        time.sleep(0.5)
        data = ser.read(100)
        if data:
            print(f"[+] Baud {baud}: {data[:50]}")
        ser.close()
    except:
        pass
```

### 3. SPI Flash Dump with flashrom
After identifying the SPI flash chip (e.g., Winbond W25Q128), connect a SOIC clip:

```bash
# Dump entire flash to file (16MB chip)
sudo flashrom -p linux_spi:dev=/dev/spidev0.0,spispeed=20000 -r firmware_dump.bin

# Verify dump integrity
sha256sum firmware_dump.bin
# Compare against known-good hash if available
```

### 4. Firmware Analysis with binwalk
Extract filesystems and look for interesting strings:

```bash
# Extract all filesystems
binwalk -Me firmware_dump.bin

# Search for hardcoded credentials
strings firmware_dump.bin | grep -iE "(password|secret|key|admin|root)" | sort -u

# Look for SSH keys or certificates
binwalk -Y firmware_dump.bin | grep -i "ssh"
```

### 5. JTAG/SWD Enumeration
Use OpenOCD to probe for debug interfaces:

```bash
# Try common JTAG/SWD pinouts
openocd -f interface/ftdi/jtagkey.cfg -f target/stm32f1x.cfg \
  -c "init; halt; flash read_bank 0 firmware.bin 0 0x100000; exit"

# If SWD is locked, try voltage glitching or clock glitching
# (requires additional hardware like ChipWhisperer)
```

## Common Pitfalls & Gotchas

1. **Assuming UART is always 3.3V** — Many IoT devices use 1.8V UART. Connecting a 3.3V adapter can fry the chip. Always measure the voltage on the TX pin with a multimeter first. If you see ~1.8V, use a level shifter or a 1.8V-tolerant USB-UART adapter like the FT232H with jumper configuration.

2. **SPI flash dump corruption** — Using too high SPI speed (>20 MHz) or poor clip contact causes bit errors. Always dump twice and compare with `diff` or `sha256sum`. If they don't match, slow down the SPI speed or re-seat the clip. Also, some flash chips have status register protection bits that must be cleared before reading.

3. **Overlooking the bootloader** — Many devices have a bootloader (U-Boot, Barebox, or proprietary) that offers a recovery shell. During boot, spam `Enter` or `Space` to interrupt. This can give you access to flash commands, environment variables, and sometimes a root shell before the main OS loads.

## Try It Yourself

1. **Find the UART on a spare router** — Disassemble an old router (e.g., TP-Link WR841N). Use a multimeter in continuity mode to find ground, then probe TX/RX pads. Connect a USB-UART adapter at 115200 baud and capture boot logs. Look for kernel messages and login prompts.

2. **Dump and analyze firmware from a development board** — Get a STM32F4 Discovery board. Use OpenOCD with an ST-Link to dump the full flash. Run `binwalk -Me` on the dump. Extract the filesystem and find at least one hardcoded string (e.g., a default password or API key).

3. **Brute-force an unknown baud rate** — Connect a USB-UART adapter to a device with unknown baud rate (e.g., a smart plug). Run the `baud_brute.py` script above. Once you find the correct baud, log in and run `cat /proc/cpuinfo` to identify the SoC.

## Next Up

Tomorrow is **Day 24: Full Review & Project: Threat Model for a Connected Door Lock**. We'll synthesize everything from the past 23 days into a complete threat model for a real product — identifying assets, trust boundaries, attack trees, and mitigations. Bring your threat modeling hat.
