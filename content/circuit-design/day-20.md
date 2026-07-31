---
title: "Day 20: Thermal Design for Circuits: Derating & Heat Dissipation"
date: 2026-07-31
tags: ["til", "circuit-design", "derating", "thermal"]
---

## What I Explored Today

I spent the day wrestling with a 5V/3A buck converter that kept hitting thermal shutdown at 85°C ambient in the thermal chamber. The datasheet said it could deliver 3A, but the fine print assumed 25°C and an infinite heatsink. Today I dug into the junction-to-ambient thermal resistance chain, learned how to properly derate components using the power dissipation curve, and calculated whether a PCB copper pour alone could save my design—or if I needed a real heatsink. The answer changed my layout entirely.

## The Core Concept

Every semiconductor has a maximum junction temperature (`Tj_max`), typically 125°C or 150°C for silicon, 175°C for SiC. The goal of thermal design is to ensure that under worst-case conditions (max ambient, max load, min airflow), the junction stays below that limit with margin. The fundamental equation is:

```
Tj = Ta + (P * Rth_ja)
```

Where:
- `Tj` = junction temperature (°C)
- `Ta` = ambient temperature (°C)
- `P` = power dissipated in the device (W)
- `Rth_ja` = thermal resistance from junction to ambient (°C/W)

The trick is that `Rth_ja` is not a fixed number—it depends on PCB copper area, airflow, and whether you use a heatsink. Datasheets typically give two values: one for a minimum footprint (often 40-60°C/W for SOT-23) and one for a "typical" 1-oz copper pour (often 20-30°C/W). The real value is somewhere in between, and you must calculate it.

**Derating** means you don't run the part at its absolute maximum. A common rule of thumb: keep `Tj` below 80-85% of `Tj_max` for reliability. For a 125°C part, that means `Tj_max_design = 100-105°C`. This gives headroom for component tolerance, thermal aging, and transient spikes.

The heat dissipation path is a series of resistances:

```
Tj → Rth_jc (junction-to-case) → Tc → Rth_cs (case-to-sink, if used) → Ts → Rth_sa (sink-to-ambient) → Ta
```

For a bare PCB-mounted part, you combine `Rth_jc` + `Rth_cb` (case-to-board) + `Rth_ba` (board-to-ambient). The board-to-ambient term is the one you control with copper area, vias, and airflow.

## Key Commands / Configuration / Code

Here's the practical workflow I use. First, calculate the worst-case power dissipation:

```python
# Thermal design check for a buck converter (LM2675-5.0)
# Input: 12V, Output: 5V @ 3A, Efficiency: 85% (from datasheet)

V_in = 12.0
V_out = 5.0
I_out = 3.0
efficiency = 0.85

P_out = V_out * I_out
P_in = P_out / efficiency
P_diss = P_in - P_out

print(f"Output power: {P_out:.1f} W")
print(f"Input power: {P_in:.1f} W")
print(f"Power dissipated: {P_diss:.2f} W")
# Output:
# Output power: 15.0 W
# Input power: 17.6 W
# Power dissipated: 2.65 W
```

Now check the thermal budget:

```python
# Thermal budget check
Tj_max = 125.0        # from datasheet
Tj_design = Tj_max * 0.8  # 80% derating
Ta_max = 85.0         # worst-case ambient

# Datasheet Rth_ja for this package (TO-263) with 1 sq inch copper
Rth_ja_min_footprint = 40.0   # °C/W, tiny pad
Rth_ja_1sqin_copper = 20.0    # °C/W, 1 oz copper, 1 sq in

# Calculate junction temp for both scenarios
Tj_min_fp = Ta_max + (P_diss * Rth_ja_min_footprint)
Tj_1sqin = Ta_max + (P_diss * Rth_ja_1sqin_copper)

print(f"Tj with min footprint: {Tj_min_fp:.1f} °C (limit {Tj_design:.1f} °C)")
print(f"Tj with 1 sq in copper: {Tj_1sqin:.1f} °C (limit {Tj_design:.1f} °C)")

# Check pass/fail
if Tj_1sqin > Tj_design:
    print("FAIL: Need heatsink or better layout")
else:
    print("PASS: 1 sq in copper pour is sufficient")
# Output:
# Tj with min footprint: 191.0 °C (limit 100.0 °C)
# Tj with 1 sq in copper: 138.0 °C (limit 100.0 °C)
# FAIL: Need heatsink or better layout
```

In this case, even with a good copper pour, we're 38°C over the design limit. The solution: either reduce output current, add forced airflow (which can halve `Rth_ba`), or attach a small heatsink to the TO-263 tab.

For PCB layout, I use these thermal via rules:

```
# KiCad / Altium thermal via pattern for power pads
# Via size: 0.3mm drill, 0.6mm pad
# Pitch: 1.0mm grid
# Count: 9-16 vias under the thermal pad
# Fill: solid (not tented) to allow solder wicking
# Connect via to bottom copper pour (same net as thermal pad)
```

## Common Pitfalls & Gotchas

**1. Datasheet Rth_ja is a lie (or at least optimistic).** The "typical" value assumes a specific PCB layout (often 1 sq inch of 1-oz copper, sometimes 2 oz). If your board is smaller, or you're using 0.5 oz copper, the real resistance is 30-50% higher. Always check the test condition footnote. I've seen designs fail because they used the "with copper" value without actually providing that copper.

**2. Thermal vias that don't work.** Vias under a thermal pad only help if they're filled with solder or have a solid connection to a bottom-side copper pour. If you tent them (cover with solder mask), they're nearly useless for heat transfer. Also, a 0.2mm drill via has significantly more resistance than a 0.3mm one—use the largest via your fab can handle.

**3. Forgetting the "hot spot" on the PCB.** Even if the junction is within limits, the PCB trace leading to the component can heat up. A 1mm trace carrying 3A will dissipate about 0.5W per inch—that's enough to raise local temperature and affect nearby components. Use a copper pour for high-current paths, not just for the thermal pad.

## Try It Yourself

1. **Calculate your own derating:** Take a component you're currently using (e.g., an LDO, MOSFET, or buck converter). Look up its `Rth_ja` for both minimum footprint and typical copper. Calculate `Tj` at your worst-case ambient and load. Apply the 80% derating rule. Does it pass?

2. **Measure the real thermal resistance:** Build a simple test board with a power resistor (e.g., a 2512 package) and a thermocouple. Apply known power (e.g., 1W, 2W, 3W) and measure the case temperature. Plot `Tc` vs. `P` — the slope is your real `Rth_ca`. Compare it to the datasheet value.

3. **Improve your layout:** Take an existing design with a thermal pad component. Add a 2x2 grid of 0.3mm thermal vias under the pad, connect them to a bottom-side copper pour, and re-run your thermal calculation. How much did your estimated `Tj` drop?

## Next Up

Tomorrow I'm switching from thermal to analog debugging. I'll cover **Debugging Analog Circuits: Oscilloscope & Multimeter Techniques** — including how to use the scope's FFT to find noise sources, why your multimeter's 10x probe setting matters more than you think, and the proper way to measure a 100mV ripple on a 12V rail without lying to yourself.
