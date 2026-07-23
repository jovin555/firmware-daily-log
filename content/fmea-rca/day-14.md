---
title: "Day 14: Statistical Process Control (SPC) for Catching Issues Early"
date: 2026-07-23
tags: ["til", "fmea-rca", "spc", "prevention"]
---

## What I Explored Today

We’ve spent the last two weeks reacting to failures—finding root causes after the product has already failed or the customer has already complained. Today I shifted gears into prevention mode and dug into Statistical Process Control (SPC). The goal: catch a process going out of control *before* it produces a defect. I implemented a real-time SPC monitor on an embedded sensor production line, using Python to simulate live data and flag out-of-control conditions. The key insight? SPC isn’t about statistics for statistics’ sake—it’s about giving operators a binary “stop or go” signal based on mathematically sound rules.

## The Core Concept

SPC is built on the idea that every process has natural variation (common cause) and unnatural variation (special cause). Common cause variation is the inherent noise in your system—tolerances, temperature drift, component aging. Special cause variation is something broken—a tool worn out, a bad batch of material, an operator error.

The magic of SPC is the control chart. You plot your process metric (e.g., output voltage, assembly torque, solder paste thickness) over time, with three horizontal lines:
- **Center Line (CL):** The historical mean of the process.
- **Upper Control Limit (UCL):** CL + 3σ (three standard deviations above the mean).
- **Lower Control Limit (LCL):** CL - 3σ.

The 3-sigma limits are not arbitrary. For a normally distributed process, 99.73% of all data points should fall within these limits if the process is stable. If a point falls outside, or if you see a run of 7+ points on one side of the center line, you have a special cause—stop the line and investigate.

Why this matters for embedded systems: We often chase intermittent failures that disappear when you reboot. SPC gives you a statistical fingerprint of the process *while it’s running*. If the mean shifts by 1.5σ but stays within spec, you won’t see a failure today—but you will tomorrow. SPC catches that shift immediately.

## Key Commands / Configuration / Code

Here’s a Python snippet that simulates a live sensor calibration process. It reads a voltage (in mV), updates a running mean and standard deviation, and applies the Western Electric rules for out-of-control detection.

```python
import numpy as np
import matplotlib.pyplot as plt
from collections import deque

# Configuration
WINDOW_SIZE = 50          # Number of samples for baseline statistics
RULE_RUN_LENGTH = 7       # Western Electric Rule 2: 7 points on same side

# Live data buffers
values = deque(maxlen=WINDOW_SIZE)
run_counter = 0           # tracks consecutive points on same side of CL
last_side = None          # 'above' or 'below'

def update_spc(new_value_mv):
    global run_counter, last_side
    values.append(new_value_mv)
    
    if len(values) < 10:  # Need minimum samples for meaningful stats
        return "COLLECTING"
    
    mean = np.mean(values)
    std = np.std(values, ddof=1)  # sample standard deviation
    ucl = mean + 3 * std
    lcl = mean - 3 * std
    
    # Rule 1: Point outside 3-sigma limits
    if new_value_mv > ucl or new_value_mv < lcl:
        return "OUT_OF_CONTROL_RULE1"
    
    # Rule 2: 7 consecutive points on same side of mean
    side = 'above' if new_value_mv > mean else 'below'
    if side == last_side:
        run_counter += 1
    else:
        run_counter = 1
        last_side = side
    
    if run_counter >= RULE_RUN_LENGTH:
        return "OUT_OF_CONTROL_RULE2"
    
    return "IN_CONTROL"

# Simulate live feed (replace with actual sensor read)
np.random.seed(42)
for i in range(100):
    # Introduce a drift after sample 50
    if i < 50:
        voltage = 1500 + np.random.normal(0, 5)  # nominal 1500 mV, σ=5
    else:
        voltage = 1510 + np.random.normal(0, 5)  # mean shifted to 1510 mV
    
    status = update_spc(voltage)
    if status.startswith("OUT_OF_CONTROL"):
        print(f"Sample {i}: {voltage:.1f} mV -> {status}")
        # In real system: trigger alarm, stop line, log to database
```

**What this does in practice:**
- The `WINDOW_SIZE` of 50 gives a stable baseline. In production, you’d pre-compute this from a known-good run.
- Rule 1 catches catastrophic failures instantly.
- Rule 2 catches the slow drift (like the +10 mV shift in the simulation) before it ever hits a spec limit.

## Common Pitfalls & Gotchas

1. **Using spec limits instead of control limits.** This is the #1 mistake. Spec limits are what the customer accepts. Control limits are what the process *can* do. If you plot spec limits on a control chart, you’ll miss shifts that are still within spec but heading toward failure. Always compute UCL/LCL from your process data, not from the datasheet.

2. **Not recalculating limits after process improvement.** If you fix a special cause and the process tightens up, your old control limits are too wide. You’ll never get an alarm again—even if the new, tighter process starts to drift. Recalculate limits after every major corrective action.

3. **Ignoring autocorrelation in embedded data.** Sensor readings from a production line are often not independent—a hot sensor reads high for several samples in a row. This violates the SPC assumption of independence. If you see false alarms from Rule 2, check your data’s autocorrelation. You may need to use a moving average chart (EWMA) instead of individual values.

## Try It Yourself

1. **Collect 100 samples from a stable process** (e.g., measure the output of a voltage regulator on 100 boards). Compute the mean and standard deviation. Plot the individual values with UCL/LCL. Do any points fall outside? If yes, investigate—your “stable” process may have a hidden special cause.

2. **Introduce a deliberate drift** in your test data (add +2% to every sample after sample 60). Run your SPC monitor and note how many samples it takes for Rule 2 to trigger. Tune the run length parameter (try 5, 7, 9) and see how it changes detection speed vs. false alarm rate.

3. **Implement a live dashboard** on a Raspberry Pi reading from an I2C sensor. Log every reading to a CSV, and have the script print “IN CONTROL” or “ALARM” to the console. Run it for an hour with the sensor at room temperature, then heat the sensor with a heat gun. Watch the control chart catch the drift before the sensor goes out of spec.

## Next Up

Tomorrow: **8D Reports: Writing for Customers & Auditors**. We’ll take the raw data from our SPC monitor and the root cause analysis from this week, and package it into a formal 8D report that satisfies automotive and aerospace auditors. No fluff—just the structure, language, and evidence they expect to see.
