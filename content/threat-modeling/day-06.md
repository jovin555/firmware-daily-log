---
title: "Day 06: Attack Surface Analysis: UART, JTAG, USB & Debug Ports"
date: 2026-07-06
tags: ["til", "threat-modeling", "debug-interfaces", "jtag"]
---

## What I Explored Today

I spent the day mapping the physical debug interface attack surface on a production Cortex-M4 board. The target had UART, JTAG, and USB DFU exposed on a header. Within 20 minutes of probing with a logic analyzer, I had the bootloader baud rate, found an unlocked JTAG TAP, and dumped the first 64KB of flash over SWD. Today’s deep dive: how to systematically enumerate, assess, and harden every debug port on an embedded device.

## The Core Concept

Debug ports are the crown jewels of an embedded attack surface. They provide direct, authenticated (or often unauthenticated) access to CPU registers, memory, and peripheral configuration. The threat model is simple: if an attacker can physically connect to a debug interface, they can extract firmware, patch execution flow, or permanently brick the device.

The key insight is that **debug interfaces are rarely disabled in production firmware**. Many teams leave JTAG/SWD enabled “just in case” for field updates, or they rely on obfuscation (e.g., hiding the header under a heatsink) rather than actual access control. A determined attacker with a $10 logic analyzer and a $20 JTAG adapter will find and exploit these ports.

The attack surface breaks into three categories:
- **UART** – serial console, often with root shell access
- **JTAG/SWD** – direct CPU debug, memory read/write, breakpoints
- **USB** – DFU, mass storage, or composite device interfaces

Each requires a different enumeration technique and different hardening strategy.

## Key Commands / Configuration / Code

### 1. UART Enumeration (Logic Analyzer + sigrok)

```bash
# Capture UART traffic on suspected TX/RX lines (pins 1-2 on header)
# Use sigrok with a cheap LA (fx2lafw)
sigrok-cli --device fx2lafw --config samplerate=10M \
  --channels D0=TX,D1=RX --time 10s --output-format csv \
  --output-file uart_capture.csv

# Decode UART at common baud rates (9600, 115200, 921600)
# PulseView or manual: look for 0x55 (alternating bits) to find baud
# Typical UART boot message pattern:
# "U-Boot 2023.04 (Apr 12 2025 - 14:22:01 +0000)"
# "Hit any key to stop autoboot:  3"
```

**Hardening UART:**
```c
// In bootloader main.c — disable UART console after boot
void disable_debug_uart(void) {
    // Disable UART clock gate
    RCC->APB1ENR &= ~RCC_APB1ENR_USART2EN;
    // Set TX/RX pins to analog mode to prevent glitching
    GPIOA->MODER |= (0x3 << (2*2)) | (0x3 << (2*3)); // PA2, PA3 = analog
    // Clear any pending RX data
    USART2->RQR |= USART_RQR_RXFRQ;
}
```

### 2. JTAG/SWD Access Control (Cortex-M)

```c
// Production firmware — lock debug access after init
void lock_debug_interface(void) {
    // Set DBGMCU->CR to disable debug in all sleep modes
    DBGMCU->CR = 0;
    
    // For STM32: set RDP level to 1 (read protection)
    // This disables SWD/JTAG access unless mass-erased
    FLASH->OPTKEYR = 0x08192A3B;  // First key
    FLASH->OPTKEYR = 0x4C5D6E7F;  // Second key
    FLASH->OPTR |= FLASH_OPTR_RDP_1; // RDP Level 1
    
    // For NXP i.MX RT: clear SRC->SCR[JTAG_EN]
    SRC->SCR &= ~SRC_SCR_JTAG_EN_MASK;
}
```

**OpenOCD attack (if unlocked):**
```bash
# Connect to target via ST-Link
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
  -c "init" \
  -c "halt" \
  -c "flash read_bank 0 firmware.bin 0x08000000 0x100000" \
  -c "exit"
```

### 3. USB DFU Enumeration

```bash
# List USB devices with DFU capability
lsusb -v | grep -A 5 "bInterfaceClass.*Application Specific"
# Typical output:
# bInterfaceClass     0xFE Application Specific
# bInterfaceSubClass  0x01 Device Firmware Upgrade

# Dump DFU descriptor (requires dfu-util)
dfu-util -l
# Found DFU: [0483:df11] ver=2200, devnum=1, cfg=1, intf=0, alt=0
```

**Hardening USB DFU:**
```c
// In USB device descriptor — set DFU to "no upload" mode
const struct dfu_function_descriptor dfu_func = {
    .bLength = sizeof(struct dfu_function_descriptor),
    .bDescriptorType = DFU_FUNCTIONAL,
    .bmAttributes = DFU_BM_ATTRIBUTE_CAN_DOWNLOAD, // No upload!
    .wDetachTimeOut = 1000,
    .wTransferSize = 1024,
    .bcdDFUVersion = 0x011A,
};
```

## Common Pitfalls & Gotchas

**1. “RDP Level 1 means secure”**
False. RDP Level 1 (read protection) only prevents flash reads over SWD/JTAG. It does **not** prevent:
- Debugging with breakpoints (you can still halt the CPU and inspect registers)
- Glitching the RDP check itself (voltage/clock glitching can bypass)
- Reading SRAM contents (which often contain keys after boot)

**2. UART is “just a debug console”**
UART is often the easiest entry point. Many bootloaders expose a shell with `md` (memory display), `mw` (memory write), and `reset` commands. If you can interrupt autoboot, you can dump the entire flash over XMODEM. Always disable the UART console in production builds.

**3. USB composite devices leak interfaces**
A device that presents as a HID keyboard for input and DFU for firmware update is a single USB descriptor. An attacker can re-enumerate the device and talk to the DFU interface even if the application code never uses it. Always check `lsusb -v` for unexpected interfaces.

## Try It Yourself

1. **UART discovery challenge**: Take any dev board with a serial header. Use a logic analyzer (or oscilloscope) to capture the boot sequence. Identify the baud rate by measuring the shortest pulse width (1 bit period). Calculate: `baud = 1 / (pulse_width_in_seconds)`. Verify with a terminal at that rate.

2. **JTAG lock verification**: On an STM32 board, write a firmware that sets RDP Level 1. After programming, attempt to connect with OpenOCD and read flash. Observe the error. Then try to halt the CPU and read `R0` — note that this still works. Document the difference between “read protected” and “debug disabled.”

3. **USB descriptor audit**: Connect any embedded device to your Linux machine. Run `lsusb -v` and count all interfaces. For each interface, identify the class (HID, CDC, DFU, etc.). If you find a DFU interface, try `dfu-util -l` to see if upload is allowed. If it is, that’s a vulnerability.

## Next Up

Tomorrow we map the OWASP Embedded/IoT Top 10 to real firmware vulnerabilities. We’ll take each category (Insecure Interfaces, Lack of Secure Update, etc.) and show exactly which CVE patterns and code smells to look for in your codebase. Bring your threat model — we’re going to cross-reference it against the industry standard.
