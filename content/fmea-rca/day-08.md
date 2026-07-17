---
title: "Day 08: Is/Is-Not Analysis: Bounding the Problem Scope"
date: 2026-07-17
tags: ["til", "fmea-rca", "is-is-not"]
---

## What I Explored Today

After spending the first week gathering data and writing problem statements, I hit a wall: the symptom space was too large. The ADC was reading high, but was it all channels? All boards? All firmware versions? I needed a scalpel, not a sledgehammer. Today I applied **Is/Is-Not Analysis** — a structured comparison technique that forces you to define exactly where the defect occurs and, critically, where it does *not* occur. This bounding step is what separates a focused root cause investigation from a wild goose chase.

## The Core Concept

Is/Is-Not Analysis is built on a deceptively simple matrix. You take your problem statement and ask: *What is the problem?* Then you ask: *What is NOT the problem, but could easily be confused with it?* You repeat this across four dimensions:

- **What** (object / component)
- **Where** (location / subsystem)
- **When** (time / event / firmware version)
- **Extent** (how many / how much)

The magic is in the contrast. By documenting what *is* and *is not* affected, you create a logical fence around the root cause. If a bug only appears on Rev C boards but not Rev B, you’ve just eliminated the entire BOM of Rev B from your search. If it only happens above 85°C, you’ve bounded the environmental envelope.

This technique is especially powerful in embedded systems because hardware and firmware interact in non-linear ways. A timing issue might only manifest on one hardware revision due to a subtle PCB trace length difference. Is/Is-Not forces you to articulate those boundaries explicitly.

## Key Commands / Configuration / Code

The analysis itself is a table, but the real work is in the data collection. Here’s a practical workflow using Python to parse log files and generate the matrix.

```python
# is_is_not_analysis.py
# Parse structured log lines to build Is/Is-Not matrix
import re
from collections import defaultdict

# Sample log format: [TIMESTAMP] [BOARD_REV] [TEMP_C] [CHANNEL] [VALUE]
log_pattern = re.compile(
    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] '
    r'\[(Rev[AB])\] '
    r'\[(\d+)\] '
    r'\[CH(\d+)\] '
    r'\[(\d+)\]'
)

def parse_logs(filepath):
    records = defaultdict(list)
    with open(filepath, 'r') as f:
        for line in f:
            m = log_pattern.match(line.strip())
            if m:
                ts, board, temp, ch, val = m.groups()
                # Flag if value > threshold (e.g., 1023 for 10-bit ADC)
                is_fault = int(val) > 1023
                records[(board, temp, ch)].append(is_fault)
    return records

def build_is_isnot_matrix(records):
    # Dimensions: board_rev, temp_range, channel
    # We'll check if ANY fault occurred in each cell
    matrix = {}
    for (board, temp, ch), faults in records.items():
        key = f"{board}|{temp}C|CH{ch}"
        matrix[key] = any(faults)
    return matrix

# Usage
# records = parse_logs("adc_logs_2026-07-17.txt")
# matrix = build_is_isnot_matrix(records)
# for cell, faulted in sorted(matrix.items()):
#     status = "IS" if faulted else "IS NOT"
#     print(f"{cell}: {status}")
```

**Key output interpretation:**
- `RevA|85C|CH0: IS` — fault present
- `RevB|85C|CH0: IS NOT` — fault absent on RevB → suspect RevA-specific hardware (e.g., a different voltage reference divider)

For real-time bounding on a target, use a shell script to compare register dumps:

```bash
#!/bin/bash
# compare_regs.sh — dump ADC registers on two boards, diff them
# Run on known-good (RevB) and failing (RevA) units
echo "=== RevA (failing) ===" > /tmp/rev_a_dump.txt
ssh user@rev-a-board "cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw" >> /tmp/rev_a_dump.txt
echo "=== RevB (good) ===" > /tmp/rev_b_dump.txt
ssh user@rev-b-board "cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw" >> /tmp/rev_b_dump.txt
diff /tmp/rev_a_dump.txt /tmp/rev_b_dump.txt
# If diff is empty, the ADC reading is identical — fault is elsewhere (e.g., analog front-end)
```

## Common Pitfalls & Gotchas

1. **Confusing "Is Not" with "Don't Know"**  
   The most dangerous row in the matrix is "Is Not" when you simply haven't tested that condition. If you haven't run the test on RevB at 85°C, you cannot claim it *is not* affected. Always verify the absence with a test, not an assumption.

2. **Over-bounding too early**  
   I once declared the problem was "only on CH0" because I only tested CH0. After expanding the test to CH1–CH7, the fault appeared everywhere. The "Is Not" column must be populated by deliberate, documented test cases — not by omission.

3. **Ignoring the "Extent" dimension**  
   A fault that occurs 30% of the time on a given board is fundamentally different from one that occurs 100% of the time. Intermittent faults require a statistical Is/Is-Not: "Is present in 3 of 10 trials" vs "Is not present in 7 of 10 trials." Record the counts, not just the boolean.

## Try It Yourself

1. **Build your own Is/Is-Not matrix** for a recent embedded bug. Use a whiteboard or spreadsheet. Columns: What, Where, When, Extent. Rows: Is, Is Not. Fill in at least three entries per cell. If any cell is empty, design a test to fill it.

2. **Write a log parser** similar to the Python example above, but for your own hardware. Modify the regex to match your log format. Run it on a dataset from a known failure and verify the matrix matches your manual analysis.

3. **Perform a "differential register dump"** between a failing and a known-good unit. Use `diff` on the outputs. Identify three registers that differ. Are they related to the symptom? If not, you've bounded the problem away from those subsystems.

## Next Up

Tomorrow we move from bounding to **D4: Root Cause Identification & Verification**. We’ll take our bounded Is/Is-Not matrix and apply cause-and-effect analysis (fishbone diagrams, 5 Whys) to pinpoint the physical, human, and latent root causes — then prove them with controlled experiments.
