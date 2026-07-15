---
title: "Day 06: Length Matching & Skew Budget Analysis"
date: 2026-07-15
tags: ["til", "high-speed-design", "length-matching", "skew"]
---

## What I Explored Today

Today I dug into length matching and skew budget analysis — the practical discipline of ensuring that all signals in a parallel bus (or differential pair) arrive at their destination within a tight timing window. While the theory is straightforward (signals travel at roughly the speed of light in the dielectric), the reality involves managing dozens of traces, accounting for package delays, and making trade-offs between serpentine routing and layer transitions. I worked through a DDR4 DQ/DQS group matching exercise and validated the skew budget against the JEDEC spec.

## The Core Concept

Length matching exists because timing margins are shrinking. At 1.6 Gbps (DDR4-3200), the bit period is 625 ps. The DQ strobe (DQS) must be centered in the DQ valid window — typically requiring skew between DQS and each DQ bit to be under 10 ps. In FR4, signal velocity is roughly 150 ps/inch (for microstrip) or 170 ps/inch (for stripline). That means 10 ps of skew corresponds to just 0.067 inches of length mismatch. You cannot afford to ignore it.

The "why" behind length matching is not about making traces equal for aesthetics — it's about skew budget. The total skew budget includes:
- **PCB trace skew**: physical length differences
- **Package skew**: internal routing differences inside the IC
- **Driver/receiver skew**: process, voltage, temperature (PVT) variations
- **Clock jitter**: uncertainty in the clock edge

Your job as the PCB designer is to minimize the PCB trace skew contribution so the system-level budget closes. Typically, you allocate 50-70% of the total budget to PCB skew, leaving the rest for silicon and jitter.

## Key Commands / Configuration / Code

### 1. Calculating Propagation Delay in Allegro PCB Editor

When setting up constraints, you need to know the propagation velocity for your stackup. In Allegro, use the `Setup -> Cross-Section` editor to define material properties, then run:

```
# In the Allegro command line:
report propagation_delay
```

This generates a report showing delay per inch for each layer. For a typical 4-layer board with 50-ohm microstrip on top layer, expect ~150 ps/inch. For stripline on inner layers, ~170 ps/inch.

### 2. Setting Up a Match Group Constraint

In Allegro Constraint Manager (CM), create a relative propagation delay (RPD) constraint:

```
# Navigate to: Electrical Constraint Set -> Relative Propagation Delay
# Create a new RPD set named "DDR4_DQ_GROUP"
# Set:
#   Scope: Pin Pair
#   Target: DQS0 (the strobe)
#   Tolerance: +/- 10 mils (adjust based on your skew budget)
#   Measurement: Longest/Shortest
```

The `+/- 10 mils` translates to roughly +/- 1.5 ps in microstrip — very tight. For DDR4, JEDEC typically allows 10-20 ps of skew between DQ and DQS, so 10 mils is a reasonable starting point.

### 3. Manual Length Calculation Script (Python)

When you need to verify lengths from an exported CSV:

```python
# length_skew_check.py
import csv

# Propagation delays (ps/inch) from your stackup
DELAY_MICROSTRIP = 150.0  # ps/inch
DELAY_STRIPLINE = 170.0

# Read exported net lengths from Allegro (CSV format: net, length_inches, layer)
with open('net_lengths.csv', 'r') as f:
    reader = csv.DictReader(f)
    nets = []
    for row in reader:
        length = float(row['length_inches'])
        layer = row['layer'].strip()
        if 'TOP' in layer or 'BOTTOM' in layer:
            delay_ps = length * DELAY_MICROSTRIP
        else:
            delay_ps = length * DELAY_STRIPLINE
        nets.append({
            'net': row['net'],
            'length': length,
            'delay_ps': delay_ps
        })

# Find max skew within the group
delays = [n['delay_ps'] for n in nets]
max_skew = max(delays) - min(delays)
print(f"Maximum skew in group: {max_skew:.1f} ps")

# Flag violations
if max_skew > 15.0:  # 15 ps budget
    print("WARNING: Skex exceeds 15 ps budget!")
```

### 4. Serpentine Routing Guidelines

When adding serpentine traces to match lengths, use these rules in your layout tool:

- **Amplitude**: 3x the line width (e.g., for 5 mil trace, use 15 mil amplitude)
- **Spacing**: 4x the line width between adjacent segments (20 mil for 5 mil trace) to avoid crosstalk
- **Minimum segment length**: at least 2x the amplitude (30 mil minimum) to avoid impedance discontinuities

In Altium, use `Tools -> Interactive Length Tuning` with these parameters. In Allegro, use `Route -> Delay Tune`.

## Common Pitfalls & Gotchas

### 1. Forgetting Package Skew
The biggest mistake is matching PCB traces perfectly while ignoring the package. For a DDR4 x16 device, the package may have 5-15 ps of internal skew between DQ0 and DQ15. If you match PCB traces to 1 ps but the package adds 12 ps, your total skew is 13 ps — possibly over budget. Always get the package skew numbers from the IBIS or datasheet and subtract them from your PCB budget.

### 2. Serpentine Coupling
Tight serpentine bends with spacing less than 3x the line width create unintended crosstalk between adjacent segments. This adds noise and can actually increase jitter. I've seen engineers use 1:1 spacing (trace width = space) and wonder why their eye diagram is closed. Always maintain 4x spacing minimum.

### 3. Layer Change Skew
When a matched group switches layers (e.g., from microstrip to stripline), the propagation delay changes by ~20 ps/inch. If one signal switches layers at a via and another doesn't, you introduce skew. Either keep all signals in the same group on the same layer, or add compensating length on the faster layer.

## Try It Yourself

1. **Calculate your stackup delay**: Open your current PCB stackup, note the dielectric constant (Dk) for each layer, and compute the propagation delay using `t_pd = 1.017 * sqrt(Dk) ns/ft` (for microstrip) or `t_pd = 1.017 * sqrt(Dk_eff) ns/ft` (for stripline). Convert to ps/inch.

2. **Audit a DDR4 match group**: Export the routed lengths for a DQ byte lane (8 DQ + 1 DQS). Calculate the skew in ps using your stackup delays. Compare to the JEDEC spec for your speed grade (e.g., DDR4-3200 allows 10 ps skew between DQ and DQS).

3. **Optimize a serpentine**: Take a trace that is 500 mils too short. Route a serpentine with 15 mil amplitude and 20 mil spacing. Measure the actual added length — does it match your expectation? Check for crosstalk by simulating the serpentine in a 2D field solver.

## Next Up

Tomorrow, I'll tackle **Via Stubs & Backdrilling for High-Speed Signals** — why a 30-mil via stub can kill your 10 Gbps signal, and how backdrilling removes that stub to clean up your eye diagram.
