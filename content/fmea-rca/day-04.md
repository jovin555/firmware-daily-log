---
title: "Day 04: D3: Interim Containment Actions"
date: 2026-07-13
tags: ["til", "fmea-rca", "d3", "containment"]
---

## What I Explored Today

Today I dug into D3 of the 8D process: Interim Containment Actions (ICA). In embedded systems, when a critical bug escapes to production—say a UART buffer overflow corrupts telemetry, or a brownout detector triggers false resets—the immediate reflex is to fix the root cause. But D3 forces a different priority: stop the bleeding *now*. I spent the morning reviewing how to implement temporary patches, hardware workarounds, and customer-side mitigations that buy time for a permanent corrective action (D4–D6). The key insight: ICA must be verifiable, reversible, and documented with zero ambiguity.

## The Core Concept

D3 exists because root cause analysis takes time—often days or weeks. Meanwhile, the defect is actively harming customers, production lines, or field units. The goal of Interim Containment Actions is to **isolate the symptom** without assuming you know the root cause. This is not a fix; it's a tourniquet.

For embedded engineers, ICA typically falls into three categories:
1. **Software workarounds** – e.g., disabling a feature, adding a watchdog reset, or patching firmware via bootloader.
2. **Hardware workarounds** – e.g., adding a pull-up resistor, swapping a component lot, or reworking a PCB trace.
3. **Process containment** – e.g., 100% inspection, burn-in testing, or quarantining suspect units.

The critical rule: every ICA must have a **verification method** and a **reversal plan**. If you add a software workaround, you must be able to remove it later when the permanent fix lands. If you rework hardware, you must track which serial numbers are affected. Without this discipline, ICAs become permanent technical debt.

## Key Commands / Configuration / Code

Below are three real-world ICA patterns I've used in production embedded systems.

### 1. Firmware Patch via Bootloader (STM32 example)
When a critical bug is found in field units, push a temporary patch through the bootloader. This assumes the bootloader is intact and the application partition is writable.

```bash
# Generate a signed patch binary (assumes STM32CubeProgrammer CLI)
STM32_Programmer_CLI -c port=SWD -w patch.bin 0x08020000 -v

# Verify the patch CRC
STM32_Programmer_CLI -c port=SWD -r8 0x08020000 0x1000 > patch_dump.bin
crc32 patch_dump.bin  # Compare with known good CRC
```

**Inline comment:** The `-v` flag enables verification after write. Always dump and CRC-check the patched region—flash corruption during field update is a common failure mode.

### 2. Disabling a Faulty Peripheral via Config File (Linux Yocto)
If a kernel driver is causing random hangs, disable it in the device tree as an interim action. This is reversible by re-enabling in the next build.

```dts
// Disable faulty SPI controller (temporary workaround)
&spi2 {
    status = "disabled";  // ICA: Disable until root cause found
    // Note: This breaks SPI2-dependent sensors. Document in release notes.
};

// Enable a software bit-bang fallback for critical sensor
&gpio4 {
    bitbang-spi {
        compatible = "spi-gpio";
        gpio-sck = <&gpio4 1 GPIO_ACTIVE_HIGH>;
        gpio-mosi = <&gpio4 2 GPIO_ACTIVE_HIGH>;
        gpio-miso = <&gpio4 3 GPIO_ACTIVE_HIGH>;
        cs-gpios = <&gpio4 4 GPIO_ACTIVE_HIGH>;
        status = "okay";
    };
};
```

**Inline comment:** The bit-bang fallback is slower but functional. This is a classic ICA—sacrifice performance for reliability.

### 3. Hardware Rework Logging (Production Line)
When a hardware defect is found (e.g., wrong capacitor value causing power-on reset), log every reworked unit with a unique identifier.

```bash
# Generate a CSV log for reworked units
echo "Serial,Date,Rework_Type,Technician,Verification_Result" > rework_log.csv
echo "SN-2024-001,2026-07-13,C101_replace,JSmith,PASS" >> rework_log.csv

# Verify rework with a boundary-scan test (JTAG)
openocd -f board/stm32f4discovery.cfg -c "init; svf rework_test.svf; exit"
```

**Inline comment:** The SVF file contains the boundary-scan vectors that verify the reworked component is correctly soldered. Always run this after manual rework.

## Common Pitfalls & Gotchas

1. **Confusing ICA with Root Cause Fix** – The most common mistake. I've seen teams spend two weeks perfecting a software workaround, only to realize the root cause was a hardware timing issue. The workaround became the "fix" and the real problem festered. ICA must be *temporary*—set a calendar reminder to revisit it.

2. **No Rollback Plan** – If you push a firmware patch via bootloader, what happens when the permanent fix arrives? You need a documented process to revert the ICA and apply the D6 solution. Without it, you accumulate "zombie workarounds" that nobody remembers.

3. **Incomplete Containment Scope** – ICAs must cover all affected units, including those in the field, in transit, and on the production line. I once saw a team contain a bug in new production but forget about 500 units already shipped. Always check the lot traceability database.

4. **Ignoring Customer Communication** – An ICA might change product behavior (e.g., reduced performance). If you don't tell the customer, they'll find out the hard way and lose trust. Issue a customer advisory notice even if the change is "internal."

## Try It Yourself

1. **Simulate a field update rollback**: On a development board (e.g., STM32 Nucleo), intentionally corrupt the application firmware, then push a temporary patch via bootloader. Document the steps to revert to the original firmware. Verify that the bootloader can distinguish between a patch and a permanent fix.

2. **Create a hardware rework log**: For a simple circuit (e.g., an LED with a resistor), simulate a component failure. Write a script that logs the serial number, date, rework action, and verification test result. Use a CRC or checksum to ensure log integrity.

3. **Draft a customer advisory**: Write a one-page notice for a hypothetical bug (e.g., "Device resets when exposed to temperatures below -20°C"). Include the ICA (e.g., "Disable low-temp mode until firmware update v2.1"), the expected impact, and the timeline for the permanent fix.

## Next Up

Tomorrow, I'll tackle **D4: Root Cause Analysis with 5 Whys**. We'll cover the technique, common pitfalls (like stopping at "human error"), and how to avoid shallow answers that lead to ineffective corrective actions. Bring your most stubborn bug—we're going deep.
