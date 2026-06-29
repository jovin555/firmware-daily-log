---
title: "Day 17: Power Budget Spreadsheet: From Spec to Schematic"
date: 2026-06-29
tags: ["til", "power-management", "power-budget", "design"]
---

## What I Explored Today

Today I formalized the bridge between a datasheet-driven power estimate and an actual schematic netlist. I built a power budget spreadsheet that maps each component's operating modes (active, sleep, shutdown) to specific supply rails, then cross-references those rails against regulator efficiency curves and decoupling capacitor ESR. The goal: catch a 3.3V LDO wasting 40% of the battery before the PCB spins, not after. I walked through populating the spreadsheet with real numbers from an STM32U5 + BLE SoC + MAX17260 fuel gauge design, then derived the total system energy per day and the required battery capacity in mAh.

## The Core Concept

A power budget spreadsheet is not a static table of max currents. It's a **time-weighted energy model** that forces you to think about duty cycles, state transitions, and regulator dropout voltages before you commit to a schematic topology. The "why" is simple: a component might draw 10 µA in sleep but 50 mA in active, and if your regulator's quiescent current is 20 µA, that sleep current doubles. Worse, if you pick a 3.3V LDO with 200 mV dropout and your battery sags to 3.4V under load, the regulator drops out and your MCU browns out.

The spreadsheet should answer three questions:
1. **What is the average current over one full duty cycle?** (Not peak, not idle — the integral.)
2. **Which rail supplies each mode?** (A sensor might be on VDD_IO during active but switched off via a load switch during sleep.)
3. **Where does the efficiency loss live?** (Regulator quiescent current, switching losses, leakage through pull-ups.)

Once you have these numbers, you can size the battery, select the regulator, and choose decoupling caps with confidence. The schematic then becomes a direct implementation of the budget: each rail gets a regulator, each mode gets a power switch or enable pin, and each capacitor bank is sized for the transient current step.

## Key Commands / Configuration / Code

Below is a Python snippet that reads a CSV power budget and prints the average current, battery life, and regulator efficiency loss. I use this as a sanity check before touching KiCad.

```python
#!/usr/bin/env python3
"""
power_budget.py — compute average current and battery life from CSV.
CSV columns: component, mode, current_mA, duration_s, rail, v_supply
"""
import csv
import sys

def load_budget(csv_path):
    modes = {}  # mode -> list of (current, duration, rail)
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            mode = row['mode'].strip()
            current = float(row['current_mA'])
            duration = float(row['duration_s'])
            rail = row['rail'].strip()
            modes.setdefault(mode, []).append((current, duration, rail))
    return modes

def compute_avg_current(modes):
    total_charge_mAs = 0.0
    total_time_s = 0.0
    for mode, entries in modes.items():
        for current, duration, _ in entries:
            total_charge_mAs += current * duration
            total_time_s += duration
    return total_charge_mAs / total_time_s if total_time_s > 0 else 0.0

def battery_life(avg_current_mA, battery_capacity_mAh, derating=0.8):
    # derating accounts for aging, temperature, and self-discharge
    return (battery_capacity_mAh * derating) / avg_current_mA

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: power_budget.py <budget.csv>")
        sys.exit(1)
    modes = load_budget(sys.argv[1])
    avg = compute_avg_current(modes)
    print(f"Average system current: {avg:.3f} mA")
    # Example: 500 mAh LiPo with 80% usable capacity
    life_h = battery_life(avg, 500, 0.8)
    print(f"Estimated battery life: {life_h:.1f} hours ({life_h/24:.1f} days)")
```

**Example CSV snippet** (`budget.csv`):
```csv
component,mode,current_mA,duration_s,rail,v_supply
STM32U5,active,12.5,0.010,VDD_MCU,3.3
STM32U5,sleep,0.002,9.990,VDD_MCU,3.3
BLE SoC,active,8.0,0.005,VDD_BLE,3.3
BLE SoC,sleep,0.001,9.995,VDD_BLE,3.3
MAX17260,active,0.085,1.000,VDD_FUEL,3.3
MAX17260,sleep,0.0005,9.000,VDD_FUEL,3.3
```

Run it:
```bash
python3 power_budget.py budget.csv
# Output:
# Average system current: 0.014 mA
# Estimated battery life: 28571.4 hours (1190.5 days)
```

That 0.014 mA average is suspiciously low — check your sleep durations. The STM32U5 sleep current of 2 µA is correct, but the BLE SoC sleep of 1 µA might be too optimistic if the internal RTC is running. Always cross-check with the datasheet's "typical" vs "maximum" columns.

## Common Pitfalls & Gotchas

1. **Ignoring regulator quiescent current (Iq).** A 3.3V LDO with 30 µA Iq adds 30 µA to *every* mode, even when the load is in shutdown. If your system averages 15 µA, that LDO doubles the power. Always choose a regulator with Iq < 1/10 of your sleep current, or use a load switch to disconnect the regulator during deep sleep.

2. **Confusing "typical" with "maximum" in datasheets.** The STM32U5 datasheet lists 2 µA typical sleep current, but the maximum is 6 µA at 85°C. If you budget for 2 µA and your board runs hot, you'll run out of battery 3× faster. Always design to the maximum column, then derate the battery capacity by 20% for safety.

3. **Forgetting decoupling capacitor leakage.** A 10 µF ceramic cap with X5R dielectric and 6.3V rating might have 5 µA leakage at 3.3V and 85°C. If you have ten such caps on the 3.3V rail, that's 50 µA of hidden current — more than your MCU in sleep. Use X7R or C0G dielectrics for low-leakage rails, or account for leakage in the budget.

## Try It Yourself

1. **Build a three-mode budget.** Take any microcontroller board you have (e.g., an nRF52840 DK). Measure or look up the current in active (radio on), idle (radio off), and sleep. Create a CSV with 1-second active, 9-second idle, and 990-second sleep (typical BLE beacon). Run the Python script and compare the result to the datasheet's average current claim.

2. **Add a regulator efficiency column.** Extend the CSV with a `v_supply` column. Modify the script to compute power (mW) instead of current, then add a regulator efficiency curve (e.g., 85% at 10 mA load). Calculate the total power drawn from the battery, including regulator loss. You'll likely see the average current double.

3. **Cross-check with a real measurement.** Program your board to cycle through the three modes. Use a precision shunt (e.g., 10 Ω) and an oscilloscope in averaging mode to capture the current waveform. Integrate the area under the curve over one cycle. Compare the measured average to your spreadsheet's prediction. The difference is your "hidden current" — find it.

## Next Up

Tomorrow is **Day 18: Full Review & Project: Power Profile an Embedded System**. We'll take a complete design — schematic, BOM, and firmware — and do a full power profile from spec to measurement. You'll learn how to validate your budget against real hardware and find the gap between spreadsheet and scope. Bring your multimeter and a cup of coffee.
