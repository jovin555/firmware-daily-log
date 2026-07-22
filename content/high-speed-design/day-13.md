---
title: "Day 13: Clock Distribution for High-Speed Systems: Skew & Jitter"
date: 2026-07-22
tags: ["til", "high-speed-design", "clock-distribution", "jitter"]
---

## What I Explored Today

Today I dug into the practical realities of clock distribution for multi-GHz systems, specifically how skew and jitter conspire to eat into your timing budget. I spent the morning simulating a 1.6 GHz DDR4 clock tree in HyperLynx, then verified the results against measured data from a 10-layer board we're spinning. The key takeaway: you can't just route a clock and hope for the best—every via, every stub, every impedance discontinuity adds deterministic jitter, and every power rail ripple adds random jitter. By the end of the day, I had a working methodology for budgeting both components.

## The Core Concept

Clock distribution is the nervous system of a high-speed digital design. The clock defines the reference moment when data is valid, and any uncertainty in that moment directly reduces the timing margin. Two enemies dominate: **skew** and **jitter**.

**Skew** is the deterministic, static difference in clock arrival times between two destinations. It comes from unequal trace lengths, different buffer delays, and process variations. You can measure it with a scope and compensate for it in layout.

**Jitter** is the dynamic, random variation of clock edge timing from cycle to cycle. It has two flavors:
- *Deterministic jitter (DJ)*: caused by crosstalk, power supply noise, and reflections. It's bounded and often periodic.
- *Random jitter (RJ)*: caused by thermal noise and flicker noise. It's Gaussian and unbounded—you can only manage its probability.

The total jitter (TJ) at a given bit error rate (BER) is approximately:
```
TJ(BER) = DJ + 2 × Q(BER) × RJ
```
Where Q(BER) is the inverse Q-function (e.g., Q(10^-12) ≈ 7.0).

For a 1.6 GHz DDR4 interface with a 625 ps UI, a typical budget might allocate 50 ps for skew and 30 ps for jitter, leaving only 545 ps for setup/hold. That's tight.

## Key Commands / Configuration / Code

Here's the practical workflow I used today for clock tree simulation and measurement.

### 1. HyperLynx DDRx Wizard — Skew Budget Entry
```
# In HyperLynx DDRx Wizard, Clock tab:
# Set "Clock Topology" = "Fly-by" (for DDR4)
# Enter per-pin skew targets:
#   DQ[0:7] max skew: 10 ps
#   DQ[8:15] max skew: 10 ps
#   DQS pair skew: 2 ps
#   CK/CK# differential skew: 1 ps
# Enable "Auto-match" with tolerance: 0.5 ps
```

### 2. Tcl Script for Length Matching in Allegro PCB Editor
```tcl
# Match clock traces to within 5 mils (approx 0.85 ps in FR4)
# Assumes 6.5 ps/inch propagation delay
set target_length 2500  ;# target length in mils
set tolerance 5          ;# tolerance in mils

foreach net {CK_P CK_N} {
    set length [get_property [get_nets $net] "length"]
    if {abs($length - $target_length) > $tolerance} {
        puts "WARNING: $net length = $length mils, out of tolerance"
    } else {
        puts "OK: $net length = $length mils"
    }
}
```

### 3. Oscilloscope Measurement for Jitter Decomposition (Keysight DSO)
```
# Setup for clock jitter measurement
:SYSTem:PRESet
:ACQuire:TYPE SEGMented
:ACQuire:SEGMented:COUNt 10000
:MEASure:JITTer:EYE:CLOCk? CK_P
# Returns: TJ@1e-12, DJ, RJ(rms), RJ(peak-peak)
# Example output: 28.3e-12, 12.1e-12, 1.02e-12, 6.12e-12
```

### 4. Python Script for Jitter Budget Calculation
```python
import numpy as np

def total_jitter(dj, rj_rms, ber=1e-12):
    """Calculate total jitter at given BER."""
    q = np.sqrt(2) * np.erfinv(1 - ber)  # ~7.0 for 1e-12
    return dj + 2 * q * rj_rms

# Example: DDR4 1600 MT/s, 625 ps UI
ui = 625e-12
dj_budget = 15e-12   # 15 ps deterministic
rj_rms = 1.5e-12     # 1.5 ps rms random

tj = total_jitter(dj_budget, rj_rms)
margin = ui - tj
print(f"Total jitter: {tj*1e12:.1f} ps")
print(f"Remaining margin: {margin*1e12:.1f} ps")
# Output: Total jitter: 36.0 ps, Remaining margin: 589.0 ps
```

## Common Pitfalls & Gotchas

1. **Ignoring via-induced skew.** A single via adds ~2-3 ps of delay per layer transition. If your clock tree uses 4 vias on one branch and 6 on another, that's 4-6 ps of skew you didn't budget for. Always count vias and match them between branches.

2. **Assuming all jitter is random.** Many engineers measure total jitter and assume it's all RJ, then wonder why their BER is worse than predicted. Always decompose jitter into DJ and RJ components. DJ from power supply noise at the switching regulator frequency (e.g., 500 kHz) will show up as a distinct bump in the jitter spectrum.

3. **Mismatched termination on clock pairs.** A 50-ohm single-ended termination on a 100-ohm differential pair creates a 25-ohm common-mode load, causing reflections that add 5-10 ps of DJ. Always use 100-ohm differential termination (two 50-ohm resistors to a virtual ground, or a single 100-ohm resistor across the pair).

## Try It Yourself

1. **Measure your clock tree skew.** Use a 4-channel scope with matched probes. Probe CK_P at the source and at the farthest load. Measure the time difference between the 50% crossing points. If it's >10 ps, check your trace lengths and via counts.

2. **Decompose jitter on a 100 MHz reference clock.** Capture 10,000 edges on a scope with jitter analysis. Record TJ, DJ, and RJ(rms). Calculate the expected BER using the formula above. Compare to the datasheet specification.

3. **Simulate a clock via in HyperLynx or Ansys.** Create a 4-layer stackup with a clock trace transitioning from top to inner layer. Measure the delay through the via. Add a second via and measure the difference. Adjust your length matching to compensate.

## Next Up

Tomorrow we tackle **Return Path Discontinuities: Plane Splits & Stitching Vias** — how a poorly placed via or a gap in the reference plane can turn a clean 10 Gbps signal into a radiating antenna. We'll cover when to stitch, how many vias to use, and why a 1 mm slot in the ground plane can cost you 3 dB of signal integrity.
