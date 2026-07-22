---
title: "Day 13: Field Failure Analysis: Returned Unit Triage for Firmware/Hardware"
date: 2026-07-22
tags: ["til", "fmea-rca", "field-failure", "triage"]
---

## What I Explored Today

Today I worked through the complete triage workflow for a batch of 12 field-returned motor controller units that had been failing with "overcurrent" fault codes after 3-6 months of deployment. The units came back from a water treatment plant, and the customer reported intermittent shutdowns that couldn't be reproduced in the lab. I walked through the systematic process of separating hardware damage from firmware bugs, using serial flash dumps, JTAG debug sessions, and careful physical inspection under a microscope. The key insight: without a structured triage protocol, you waste days chasing phantom issues that are actually physical degradation masked by firmware error handling.

## The Core Concept

Field failure triage is fundamentally different from bench testing. In the lab, you control the environment. In the field, the unit has experienced real-world thermal cycling, vibration, humidity, and electrical noise that you cannot easily replicate. The core principle is **progressive disclosure of evidence** — you must preserve the unit's state before you destroy it.

The triage pyramid works like this:
1. **Non-invasive** — read logs, capture flash, measure external voltages
2. **Semi-invasive** — open enclosure, inspect for physical damage, probe test points
3. **Invasive** — desolder components, decap ICs, cross-section PCBs

You always start at the top. The most common mistake is going straight to invasive methods (like reflowing a suspected BGA) and losing the firmware evidence that would have told you the real story.

For firmware/hardware boundary issues, the critical question is: *Did the firmware correctly detect a hardware fault, or did the firmware itself cause the hardware to fail?* The answer lives in the non-volatile logs, the fault register snapshots, and the state of the watchdog timer at the moment of failure.

## Key Commands / Configuration / Code

### 1. Preserving the Firmware State via SWD/JTAG

Before powering the unit, connect via a debug probe and dump the full flash and RAM contents. On an STM32-based controller:

```bash
# OpenOCD script to dump flash and RAM before any power cycle
# This preserves the exact state at time of failure

openocd -f interface/stlink-v2.cfg -f target/stm32f4x.cfg \
  -c "init" \
  -c "reset halt" \
  -c "flash read_bank 0 /tmp/firmware_dump.bin 0x08000000 0x100000" \
  -c "dump_image /tmp/ram_dump.bin 0x20000000 0x30000" \
  -c "shutdown"
```

### 2. Extracting the Fault Log from EEPROM/FRAM

Most industrial controllers store a circular fault log. Here's a Python script to parse a common binary format:

```python
# parse_fault_log.py - Extract and decode fault records from a 64KB EEPROM dump
import struct

FAULT_RECORD_SIZE = 32  # bytes per fault entry
MAX_RECORDS = 2000

def parse_fault_log(binary_data):
    """Parse a circular fault log buffer. Returns list of fault dicts."""
    # First 4 bytes: write pointer (next free slot)
    write_ptr = struct.unpack('<I', binary_data[0:4])[0]
    
    # Records start at offset 4
    records = []
    for i in range(MAX_RECORDS):
        offset = 4 + (i * FAULT_RECORD_SIZE)
        if offset + FAULT_RECORD_SIZE > len(binary_data):
            break
        
        record_bytes = binary_data[offset:offset + FAULT_RECORD_SIZE]
        fault_code, timestamp, param1, param2 = struct.unpack('<HIHH', record_bytes)
        
        # Only process non-zero records
        if fault_code == 0xFFFF or fault_code == 0:
            continue
            
        records.append({
            'fault_code': f'0x{fault_code:04X}',
            'timestamp_s': timestamp,
            'adc_current_ma': param1 * 10,  # scale factor from firmware
            'vbus_voltage_mv': param2 * 100
        })
    
    return records

# Usage
with open('eeprom_dump.bin', 'rb') as f:
    data = f.read()
faults = parse_fault_log(data)
for f in faults[:5]:  # Show last 5 faults
    print(f"Fault {f['fault_code']} at t={f['timestamp_s']}s, "
          f"I={f['adc_current_ma']}mA, Vbus={f['vbus_voltage_mv']}mV")
```

### 3. Hardware Triage: Measuring Gate Drive Signals

After firmware analysis, power the unit with a current-limited bench supply (set to 500mA max to prevent further damage). Probe the gate drive signals with a differential probe:

```bash
# Oscilloscope setup for gate drive analysis (Tektronix MSO)
# Channel 1: High-side gate (differential, 10x probe)
# Channel 2: Low-side gate (differential, 10x probe)
# Trigger: Falling edge on Channel 1, DC coupling, 50% threshold

# Key measurements to capture:
MEASUREMENT: CH1 FREQUENCY
MEASUREMENT: CH2 FREQUENCY  
MEASUREMENT: CH1 RISE_TIME
MEASUREMENT: CH2 FALL_TIME
MEASUREMENT: CH1+CH2 DELAY  # Dead-time measurement
```

## Common Pitfalls & Gotchas

1. **Powering the unit without first dumping the flash.** I've seen engineers plug in a returned board, watch it boot normally, and then wonder why the fault log is empty. The power-on reset sequence often clears volatile fault registers. Always dump flash and RAM *before* applying power if the unit has a backup battery or supercapacitor keeping the RTC alive. If the unit is completely dead, dump the external SPI flash first — it's non-volatile and won't be affected by power-up.

2. **Assuming the fault code is accurate.** Firmware fault handlers can be triggered by secondary effects. I once spent three days chasing an "overvoltage" fault that was actually caused by a failing voltage reference IC — the ADC was reading high because the reference voltage had drifted, not because the bus voltage was actually high. Always cross-reference fault codes with independent measurements (e.g., compare the reported ADC value with a multimeter reading at the same test point).

3. **Skipping the visual inspection under magnification.** A cracked solder joint on a QFN package can look perfect to the naked eye but show clear "head-in-pillow" defects at 50x magnification. I use a digital microscope at 20-100x and look specifically at: BGA balls (check for corner cracks), connector pins (fretting corrosion), and electrolytic capacitors (bulging tops are obvious, but check for leaked electrolyte under the rubber seal).

## Try It Yourself

1. **Build a fault log parser for your own product.** Take a production unit, intentionally trigger a fault (e.g., short the output), and dump the EEPROM. Write a Python script that decodes the raw binary into human-readable timestamps and fault codes. Verify the timestamp matches your lab clock.

2. **Perform a "blind" triage on a known-bad unit.** Have a colleague introduce a subtle hardware fault (e.g., remove a decoupling capacitor or loosen a connector) without telling you what it is. Follow the triage pyramid: dump flash first, then inspect visually, then probe. Document your findings at each step before moving to the next.

3. **Measure and characterize gate drive dead-time.** On a motor controller or half-bridge, use a differential probe to measure the high-side and low-side gate signals. Calculate the dead-time between one turning off and the other turning on. Compare this to the firmware's configured dead-time. A mismatch of more than 100ns can indicate gate driver degradation or PCB parasitic issues.

## Next Up

Tomorrow we shift from analyzing individual failures to catching them before they escape: **Statistical Process Control (SPC) for Catching Issues Early**. We'll cover how to set up control charts for key manufacturing parameters (like solder paste volume and torque values) and use Western Electric rules to detect process drift before it creates field failures.
