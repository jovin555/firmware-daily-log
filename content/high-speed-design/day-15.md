---
title: "Day 15: Simultaneous Switching Noise (SSN) & Ground Bounce"
date: 2026-07-24
tags: ["til", "high-speed-design", "ssn", "ground-bounce"]
---

## What I Explored Today

Today I dug into Simultaneous Switching Noise (SSN) and its most visible symptom: ground bounce. I’ve seen this before on a 32-bit DDR bus where every data line toggled from 0 to 1 at once, and the core voltage rail drooped by nearly 200 mV. That glitch corrupted the adjacent address line. SSN isn’t just a theoretical SI topic—it’s the reason your FPGA’s I/O bank crashes when you enable all outputs simultaneously. I spent the day modeling the parasitic inductance in return paths and verifying mitigation strategies with a real oscilloscope capture.

## The Core Concept

SSN occurs when multiple outputs switch at the same time, drawing a sudden surge of current through the shared power delivery network (PDN). The fundamental equation is:

\[
V_{noise} = N \times L_{total} \times \frac{di}{dt}
\]

Where:
- \( N \) = number of simultaneously switching outputs (SSOs)
- \( L_{total} \) = total inductance in the loop (package + PCB via + plane inductance)
- \( di/dt \) = rate of current change per output

The noise voltage appears across the parasitic inductance of the ground or power return path. If the ground reference at the driver rises (ground bounce), the output voltage seen by the receiver appears lower than intended. If the power rail collapses (Vdd droop), the output high level drops. Both cause logic errors, setup/hold violations, and false clocking.

The worst-case scenario is when all outputs switch in the same direction (e.g., all 0→1). The total current change is additive. For a 32-bit bus with 20 pF load per pin, 3.3 V swing, and 1 ns rise time, the instantaneous current per pin is \( I = C \times dV/dt = 20\text{pF} \times 3.3\text{V} / 1\text{ns} = 66\text{mA} \). With 32 pins, that’s 2.1 A of transient current. If the package inductance is 5 nH, the ground bounce is \( 2.1 \times 5 = 10.5\text{V} \)—enough to destroy logic thresholds.

Mitigation focuses on reducing \( L \) and \( di/dt \):
- **Reduce loop inductance**: Use multiple ground/power pins per I/O bank, short vias, solid reference planes.
- **Spread switching edges**: Add skew or use slew-rate-limited outputs.
- **Decouple locally**: Place 0.1 µF + 0.01 µF capacitors within 50 mils of each power pin.
- **Use differential signaling**: Common-mode rejection cancels SSN.

## Key Commands / Configuration / Code

### 1. IBIS Model SSN Simulation (using HyperLynx or similar)

```bash
# HyperLynx LineSim command to set SSO count and check noise margin
# Use IBIS model for a 3.3V LVCMOS driver
SET_DRIVER_MODEL "lvcmos33.ibs" PIN=U1.1
SET_LOAD_MODEL "20pF" PIN=U2.1
SET_SIMULTANEOUS_SWITCHING_COUNT 16
RUN_SSN_ANALYSIS FREQUENCY=100MHz
# Output: Ground bounce peak = 1.2V, exceeds V_IL_max (0.8V)
```

### 2. FPGA I/O Bank Slew Rate Control (Xilinx Vivado Tcl)

```tcl
# Reduce di/dt by setting slow slew rate on all outputs in bank 34
set_property SLEW SLOW [get_ports {data_out[*]}]
# Also enable output drive strength to minimum (8mA)
set_property DRIVE 8 [get_ports {data_out[*]}]
# Check timing closure after change
report_timing -from [get_ports data_out[*]] -to [get_ports data_in[*]]
```

### 3. PCB Stackup Inductance Calculation (Python snippet)

```python
# Calculate loop inductance for a microstrip trace over a ground plane
# Formula: L_loop = 5.08 * h * ln(2*pi*h / w)  (nH/inch)
h = 0.008  # dielectric height in inches (8 mil FR4)
w = 0.005  # trace width in inches (5 mil)
L_per_inch = 5.08 * h * (2.71828 ** (2 * 3.14159 * h / w))
print(f"Loop inductance: {L_per_inch:.2f} nH/inch")
# For a 0.5 inch trace, L_total = 0.5 * L_per_inch
```

### 4. Oscilloscope Measurement for Ground Bounce

```bash
# Setup on a 4-channel scope (e.g., Keysight Infiniium)
# Channel 1: Probe output pin (AC coupled, 1 MOhm)
# Channel 2: Probe adjacent quiet output pin (DC coupled, 50 Ohm)
# Trigger on rising edge of Channel 1
# Measure: V_peak of Channel 2 during switching event
# Expected: < 300 mV for 3.3V logic
```

## Common Pitfalls & Gotchas

1. **Assuming one decoupling cap per pin is enough**  
   A single 0.1 µF cap has ~2 nH ESL. At 100 MHz, its impedance is 1.25 Ω. For 2 A transient, that’s 2.5 V drop. You need multiple caps in parallel (reduces ESL) and a bulk cap (10–100 µF) to handle the low-frequency content.

2. **Ignoring package inductance**  
   The BGA package’s power/ground balls have inductance too. A 0.5 mm solder ball + via stub adds ~0.5 nH. Multiply by 32 SSOs, and you’ve added 16 nH to the loop. Always check the package IBIS model’s `[Pin]` section for `R_pkg`, `L_pkg`, `C_pkg`.

3. **Measuring ground bounce at the wrong point**  
   Probing the output pin relative to board ground gives you the *output* voltage, not the ground bounce. To see ground bounce, probe a *quiet* output pin (one that isn’t switching) relative to board ground. That pin’s voltage will show the ground reference shift.

## Try It Yourself

1. **Simulate SSN in your favorite SI tool**  
   Take a 16-bit bus with 3.3V LVCMOS drivers, 15 pF loads, and 2 ns rise time. Set SSO count to 16. Record the ground bounce peak. Then add 0.1 µF decoupling caps at each driver’s power pin and rerun. Compare the noise reduction.

2. **Measure ground bounce on a real board**  
   Find a GPIO bank on an FPGA or MCU that drives 8+ outputs. Program all outputs to toggle at 50 MHz. Probe a quiet output pin (set to logic 0) with a scope. Trigger on a switching output. Measure the peak-to-peak noise on the quiet pin. If > 300 mV, add a 0.01 µF cap near the bank’s power pin.

3. **Calculate your PDN inductance budget**  
   For a 3.3 V rail with 100 mV allowed noise and 32 SSOs each drawing 50 mA, calculate the maximum allowed loop inductance. Use \( L_{max} = V_{noise} / (N \times di/dt) \). Assume 1 ns rise time. Compare to your PCB’s estimated inductance per via.

## Next Up

Tomorrow: **Test & Measurement: TDR, VNA & Eye Diagram Capture** — I’ll walk through setting up a time-domain reflectometer to find impedance discontinuities, using a vector network analyzer for S-parameter extraction, and capturing an eye diagram to quantify jitter and noise margin. Bring your oscilloscope probes.
