---
title: "Day 26: Full Review & Bring-up Checklist"
date: 2026-07-08
tags: ["til", "embedded-linux", "review", "bringup"]
---

## What I Explored Today

After weeks of bootloader configuration, kernel hacking, rootfs assembly, and device driver integration, I stepped back today to build a comprehensive bring-up checklist. This isn't just a list of commands—it's a structured review process that catches the subtle failures that derail embedded Linux projects. I've been burned by a missing regulator, a wrong pinmux, and a silent filesystem corruption that only showed up in production. Today I formalized the exact sequence I now run on every new board, from power-on to a working shell, with validation checkpoints at each stage.

## The Core Concept

Embedded Linux bring-up is a stack of dependencies: hardware must be alive before the boot ROM runs, the boot ROM must find a valid bootloader before it loads the kernel, the kernel must initialize clocks and memory before it can mount a rootfs, and init must start before any application runs. The failure modes are cascading—a 1.8V rail that's 50mV low can cause the boot ROM to read garbage from eMMC, which looks like a corrupted bootloader, which you'll waste hours debugging with JTAG when the real problem is on the power supply.

A bring-up checklist forces you to verify each layer independently before trusting the next. It's the difference between "the kernel panics at random" and "I know the rootfs is intact because I verified the checksum after flashing." The checklist also serves as a living document for the team—when a new engineer joins, they can reproduce the bring-up without tribal knowledge.

## Key Commands / Configuration / Code

### 1. Power Rail Validation (before any firmware)
```bash
# Measure all rails with a multimeter or scope
# Target: 1.8V ±2%, 3.3V ±3%, VDD_CORE (check datasheet)
# Use i2cget to read PMIC registers if available
i2cget -y 0 0x5a 0x00 w  # Example: read PMIC status register

# Check power sequencing with oscilloscope
# Typical sequence: VDD_CORE -> VDD_IO -> VDD_DDR
# Minimum delay between rails: 1ms (check SoC datasheet)
```

### 2. Boot ROM and Bootloader Verification
```bash
# Check boot mode pins (e.g., SD boot vs eMMC)
gpioinfo | grep BOOT_MODE  # Verify pin states match expected boot source

# Read boot ROM version (if accessible via debug UART)
# On i.MX8M, UART shows: "Boot ROM version: 1.0.0"
# On STM32MP1, UART shows: "BootROM: Starting..."

# Verify bootloader checksum before flashing
sha256sum u-boot-spl.bin > spl.sha256
# Compare with known-good hash from build server
```

### 3. Kernel Bring-up Validation
```bash
# Add earlycon to kernel command line for earliest possible debug
# In bootargs: earlycon=uart8250,mmio32,0x30890000,115200n8

# Check dmesg for critical errors after boot
dmesg | grep -E "error|fail|panic|oops|BUG" | grep -v "ignored"

# Verify all required clocks are enabled
cat /sys/kernel/debug/clk/clk_summary | grep -E "mmc|usb|eth"

# Check regulator constraints match hardware
cat /sys/class/regulator/regulator.*/microvolts
# Should match schematic values ±5%
```

### 4. Rootfs Integrity Check
```bash
# After flashing, verify filesystem checksum
# For squashfs:
unsquashfs -s rootfs.squashfs | grep "Filesystem size"
# Compare to expected size from build

# For ext4 on eMMC:
fsck.ext4 -n /dev/mmcblk0p2  # -n = read-only check

# Verify critical binaries exist and are executable
for bin in /sbin/init /bin/sh /lib/ld-linux.so.*; do
    [ -x "$bin" ] && echo "OK: $bin" || echo "MISSING: $bin"
done
```

### 5. Network and Peripheral Bring-up
```bash
# Verify MAC address is valid (not all zeros or all ones)
cat /sys/class/net/eth0/address | grep -v "00:00:00:00:00:00\|ff:ff:ff:ff:ff:ff"

# Test I2C device detection
i2cdetect -y 0  # Compare output to expected device addresses

# Check SPI device registration
cat /sys/bus/spi/devices/*/modalias
# Should match driver name in device tree
```

## Common Pitfalls & Gotchas

**1. The "Silent Power Good" Trap**
Many PMICs assert POWER_GOOD before all rails are stable. I've seen boards where VDD_CORE is at 0.9V (target 1.1V) but the PMIC reports "good" because the threshold is set too low. Always measure with a scope, not just a multimeter—the multimeter averages out the ripple that causes intermittent boot failures.

**2. Bootloader Size Exceeds SRAM**
SPL or secondary bootloader must fit in internal SRAM (typically 128KB-512KB). I once spent two days debugging why U-Boot SPL wouldn't load, only to find a debug build had bloated past the 256KB limit. Always check the actual binary size:
```bash
ls -l u-boot-spl.bin
# Compare to SRAM size from SoC datasheet (e.g., 0x40000 for 256KB)
```

**3. Device Tree Overlay Ordering**
When using multiple overlays, the kernel applies them in the order listed in the bootloader's `overlays` variable. If overlay A depends on a node created by overlay B, the kernel silently skips the dependency and you get a "failed to create node" warning that's easy to miss. Always list overlays in dependency order, and verify with:
```bash
dtc -I fs -O dts /sys/firmware/devicetree/base > /tmp/merged.dts
# Check that all expected nodes exist
```

## Try It Yourself

1. **Build a bring-up checklist for your current board**: Start with power rails, then boot ROM, then bootloader, then kernel, then rootfs. For each step, write the exact command or measurement that proves the step passed. Include the expected values (voltage, timing, checksum).

2. **Simulate a failure**: Disable one power rail (e.g., remove a jumper on VDD_IO) and observe the boot behavior. Document exactly what the UART shows. This trains you to recognize the failure signature when it happens in the field.

3. **Create a "golden boot" log**: Capture the full boot log from a known-good board. Run `diff` against every new board's boot log. Automate this in your CI pipeline—it catches regressions that manual review misses.

## Next Up: Full Review

Tomorrow we'll do a complete end-to-end review of the entire embedded Linux stack we've built over the past 25 days. We'll walk through a real bring-up scenario, from reading the schematic to running the first application, with all the validation checkpoints and debugging techniques we've covered. Bring your own board's boot log—we'll analyze it together.
