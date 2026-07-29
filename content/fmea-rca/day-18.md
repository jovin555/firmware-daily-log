---
title: "Day 18: Full Review & Project: 8D Report for a Field-Returned Embedded Device"
date: 2026-07-29
tags: ["til", "fmea-rca", "review", "project"]
---

## What I Explored Today

Today I completed a full 8D (Eight Disciplines) problem-solving report for a field-returned embedded device—a battery management system (BMS) controller that failed after 18 months in service. The device exhibited intermittent communication loss on the CAN bus, eventually causing a complete system lockup. Using the 8D methodology, I walked through each discipline: forming the team, defining the problem, implementing containment, identifying root cause, choosing permanent corrective actions, validating, preventing recurrence, and closing. This was not a theoretical exercise; I used real oscilloscope captures, firmware version diffs, and production test logs to reconstruct the failure chain.

## The Core Concept

The 8D process is not a checklist—it’s a forensic reconstruction of a failure with a focus on systemic prevention. For embedded engineers, the trap is jumping to “fix the firmware” or “replace the component” without proving the causal chain. The 8D forces you to separate symptoms from root cause. In this BMS case, the symptom was CAN bus silence. The immediate cause was a corrupted bootloader vector table. The root cause? A race condition in the production test fixture that wrote a partial firmware image during a power glitch. Without 8D, we would have blamed the CAN transceiver or the MCU’s internal oscillator. Instead, we found a manufacturing process flaw.

The key insight: **8D is about evidence, not intuition.** Every D (discipline) requires documented proof: containment must be verified, root cause must be reproducible, and corrective actions must have measurable pass/fail criteria.

## Key Commands / Configuration / Code

Below is a real snippet from my analysis—a Python script that parsed the device’s crash dump logs to correlate CAN bus errors with firmware version and production batch.

```python
#!/usr/bin/env python3
# parse_crash_dump.py - Extract CAN error counters and firmware version from field-returned BMS

import csv
import re

def parse_dump(filepath):
    """Parse a binary crash dump for CAN error counters and firmware version."""
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # Firmware version at offset 0x100 (4 bytes, ASCII)
    fw_version = data[0x100:0x104].decode('ascii', errors='ignore').strip('\x00')
    
    # CAN error counters at offset 0x200 (2 bytes each, little-endian)
    tx_err_cnt = int.from_bytes(data[0x200:0x202], 'little')
    rx_err_cnt = int.from_bytes(data[0x202:0x204], 'little')
    
    return {
        'fw_version': fw_version,
        'tx_err_cnt': tx_err_cnt,
        'rx_err_cnt': rx_err_cnt,
        'total_errors': tx_err_cnt + rx_err_cnt
    }

# Process all dumps from returned units
results = []
for unit_id in ['BMS-042', 'BMS-087', 'BMS-113']:
    dump = parse_dump(f'crash_dumps/{unit_id}.bin')
    results.append(dump)
    print(f"{unit_id}: FW={dump['fw_version']}, TX_errs={dump['tx_err_cnt']}, RX_errs={dump['rx_err_cnt']}")

# Output to CSV for 8D report
with open('can_error_analysis.csv', 'w', newline='') as csvfile:
    fieldnames = ['unit_id', 'fw_version', 'tx_err_cnt', 'rx_err_cnt', 'total_errors']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for i, unit_id in enumerate(['BMS-042', 'BMS-087', 'BMS-113']):
        writer.writerow({'unit_id': unit_id, **results[i]})
```

The script revealed that all three returned units had firmware version `2.1.3`—the same version produced during a 2-hour window when the production line’s power supply had a known droop. This was the first clue linking the failure to manufacturing.

For containment, I wrote a quick test to verify the bootloader integrity on all in-field units:

```bash
# Verify bootloader CRC on all BMS units in the field via CAN bootloader command
# Command: 0x3E (bootloader CRC request), response: 4-byte CRC
cansend can0 123#3E000000
candump can0 | grep "123" | while read line; do
    crc=$(echo $line | awk '{print $3}' | cut -c5-12)
    expected_crc="A5B6C7D8"
    if [ "$crc" != "$expected_crc" ]; then
        echo "FAIL: Unit CRC mismatch (got $crc, expected $expected_crc)"
    else
        echo "PASS: Bootloader CRC valid"
    fi
done
```

## Common Pitfalls & Gotchas

1. **Confusing correlation with causation.** Just because all failed units have firmware version 2.1.3 doesn’t mean the firmware is buggy. In my case, the firmware was fine—the production test fixture corrupted the flash during programming. Always reproduce the failure in a controlled environment before declaring root cause.

2. **Skipping containment verification.** Many teams implement a containment action (e.g., “reflash all field units”) but never verify it worked. I saw a case where the reflash tool itself had a bug, corrupting 5% of units. Always add a post-containment test with a known-good reference.

3. **Ignoring the “D4” trap: multiple root causes.** The 8D expects one root cause, but embedded failures often have a chain. In this BMS, the root cause was the power glitch during production, but the enabling factor was that the bootloader didn’t have a CRC check before jumping to the application. Document both as the “root cause” and the “contributing factor” in D4.

## Try It Yourself

1. **Reproduce a field failure in the lab.** Take a returned device, connect it to a CAN bus analyzer (e.g., PCAN-USB), and replay the traffic log from the field. Use Wireshark’s CAN dissector to see if the failure reproduces. If not, your containment plan is based on a guess.

2. **Write a bootloader integrity test.** Modify the script above to check the bootloader CRC on every power-up. Log the result to a reserved EEPROM sector. This is a cheap way to catch partial writes or flash corruption before the application runs.

3. **Create a fishbone (Ishikawa) diagram for your own product.** List every possible cause under categories: hardware, firmware, manufacturing, environment, and user. Then cross-reference with field return data. You’ll likely find a cause you never considered (e.g., “operator unplugged the programmer mid-flash”).

## Next Up

Tomorrow is **Full Review**—I’ll step back and evaluate the entire 8D process for this BMS project: what worked, what didn’t, and how to improve the next RCA. We’ll also discuss when 8D is overkill and a simple 5-Why is better.
