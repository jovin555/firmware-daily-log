---
title: "Day 18: HIL Power Measurement: Automated Current Profiling"
date: 2026-06-30
tags: ["til", "hil-testing", "power", "measurement"]
---

## What I Explored Today

Today I automated the current profiling workflow for a 48V automotive ECU under HIL test. Instead of manually probing current with a DMM and logging by hand, I wired a precision shunt resistor into the DUT power rail, connected it to a NI PXIe-4309 digitizer, and wrote a Python script that sweeps the ECU through its operational modes while recording current draw at 10 kS/s. The result: a complete power profile—idle, active, full load, and fault—ready for regression comparison in CI.

## The Core Concept

Power measurement in HIL isn't just about verifying the DUT doesn't blow a fuse. It's about catching regressions in power management firmware, validating sleep-mode current budgets, and ensuring thermal limits aren't violated under worst-case load. Manual current logging is error-prone, slow, and misses transient spikes that last microseconds.

Automated current profiling solves this by synchronizing the HIL's stimulus (voltage ramps, CAN messages, digital I/O) with high-speed data acquisition on the power rail. The key insight: you don't need a dedicated power analyzer. A low-side shunt resistor (10–50 mΩ) and a differential input on a digitizer or DAQ card gives you microamp resolution at kilohertz bandwidth. The HIL real-time processor triggers acquisition exactly when the DUT transitions states, so every profile is aligned to the same time-zero.

The output is a CSV with columns for timestamp, current, voltage, and DUT state. CI then compares this against a golden profile using RMS error and peak-current thresholds. If the new firmware draws 12 mA in sleep instead of 8 mA, the pipeline fails.

## Key Commands / Configuration / Code

Here's the actual NI-DAQmx Python code I used, running on the HIL host PC. The shunt is a 20 mΩ, 3 W resistor on the low side of the 48 V rail, wired to PXIe-4309 AI0+ and AI0-.

```python
import nidaqmx
import numpy as np
import csv
from time import sleep

# Configuration
SHUNT_RESISTOR = 0.020  # 20 mOhm
SAMPLE_RATE = 10000     # 10 kS/s
SAMPLES_PER_CHANNEL = 50000  # 5 seconds of data
CHANNEL = "PXI1Slot2/ai0"
OUTPUT_CSV = "current_profile_run18.csv"

def measure_current():
    """Acquire voltage across shunt, convert to current, return array."""
    with nidaqmx.Task() as task:
        # Differential mode, ±10V range (safe for 48V rail via voltage divider)
        task.ai_channels.add_ai_voltage_chan(
            CHANNEL,
            min_val=-10.0,
            max_val=10.0,
            terminal_config=nidaqmx.constants.TerminalConfiguration.DIFF
        )
        task.timing.cfg_samp_clk_timing(
            rate=SAMPLE_RATE,
            samps_per_chan=SAMPLES_PER_CHANNEL
        )
        # Trigger acquisition on rising edge of PFI0 (connected to DUT state change)
        task.triggers.start_trigger.cfg_dig_edge_start_trig(
            trigger_source="/PXI1Slot2/PFI0",
            trigger_edge=nidaqmx.constants.Edge.RISING
        )
        data = task.read(number_of_samples_per_channel=SAMPLES_PER_CHANNEL)
    
    # Convert voltage to current: I = V / R
    current = np.array(data) / SHUNT_RESISTOR
    return current

def save_profile(current, state_label):
    """Append timestamped data to CSV with state label."""
    timestamps = np.arange(len(current)) / SAMPLE_RATE
    with open(OUTPUT_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        for t, i in zip(timestamps, current):
            writer.writerow([t, i, state_label])

# Main sequence: cycle DUT through states via CAN
states = ["SLEEP", "ACTIVE", "FULL_LOAD", "FAULT"]
for state in states:
    print(f"Setting DUT to {state}...")
    # Send CAN message to DUT (example using python-can)
    # can_bus.send(can.Message(arbitration_id=0x100, data=[state_code], is_extended_id=False))
    sleep(0.5)  # Settling time
    
    print("Triggering acquisition...")
    current_data = measure_current()
    save_profile(current_data, state)
    print(f"  Captured {len(current_data)} samples for {state}")

print(f"Profile saved to {OUTPUT_CSV}")
```

**CI comparison script snippet (pytest):**

```python
import pandas as pd
import numpy as np

GOLDEN = pd.read_csv("golden_current_profile.csv")
NEW = pd.read_csv("current_profile_run18.csv")

for state in ["SLEEP", "ACTIVE", "FULL_LOAD", "FAULT"]:
    golden_state = GOLDEN[GOLDEN["state"] == state]["current"]
    new_state = NEW[NEW["state"] == state]["current"]
    rmse = np.sqrt(np.mean((golden_state - new_state) ** 2))
    peak_diff = np.max(np.abs(golden_state - new_state))
    assert rmse < 0.002, f"{state} RMSE {rmse:.4f} A exceeds 2 mA"
    assert peak_diff < 0.010, f"{state} peak diff {peak_diff:.4f} A exceeds 10 mA"
```

## Common Pitfalls & Gotchas

1. **Shunt placement matters.** A low-side shunt (between DUT ground and system ground) is simpler but breaks ground isolation. If your DUT communicates via CAN or Ethernet, the ground offset can corrupt data. Use a high-side shunt with a differential amplifier, or an isolated DAQ module. I wasted two days debugging CAN CRC errors before realizing the shunt was injecting ground noise.

2. **Trigger jitter ruins alignment.** If your digital trigger line has noise or the DUT state transition has a variable delay, the acquisition start time drifts. Always add a pre-trigger buffer (set `samps_per_chan` to capture 10% before the trigger) so you can align profiles in post-processing using cross-correlation.

3. **Shunt power rating.** At 48 V and 5 A load, a 20 mΩ shunt dissipates only 0.5 W—fine. But during a fault condition, the DUT might draw 20 A for 100 ms. That's 8 W peak. If your shunt is only rated for 3 W, it heats up, resistance drifts, and your measurement accuracy goes out the window. Always derate by 3x for transient peaks.

## Try It Yourself

1. **Build a shunt fixture.** Wire a 10 mΩ, 5 W shunt into the low side of a bench supply feeding a microcontroller board (e.g., STM32 Nucleo). Connect a scope probe across the shunt and capture the current spike when the board boots. Verify the peak matches your calculation (e.g., 3.3 V / 0.01 Ω = 330 A? No—the shunt sees the actual current, not the rail voltage).

2. **Write a trigger script.** Modify the Python code above to use a software trigger instead of hardware (remove the `cfg_dig_edge_start_trig` line). Instead, start acquisition, then send a CAN message, then stop after 1 second. Compare the alignment of the current step between software and hardware triggering—you'll see the jitter.

3. **Automate a golden profile comparison.** Capture a current profile for your DUT in "idle" mode. Then artificially increase the idle current by 5 mA (e.g., add a resistor in parallel). Run your CI comparison script and verify it fails. Tune the RMSE threshold until it catches the 5 mA change but passes normal variation.

## Next Up

Tomorrow is **Day 19: Full Review & Project: Complete HIL Pipeline**. I'll tie together everything from the past 18 days—test orchestration, plant models, fault injection, data logging, and CI integration—into a single, runnable pipeline for a brake-by-wire ECU. We'll walk through the Jenkinsfile, the HIL configuration, and the pass/fail criteria end to end.
