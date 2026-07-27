---
title: "Day 16: Test & Measurement: TDR, VNA & Eye Diagram Capture"
date: 2026-07-27
tags: ["til", "high-speed-design", "tdr", "vna"]
---

## What I Explored Today

Today I dove into the three pillars of high-speed channel validation: Time-Domain Reflectometry (TDR), Vector Network Analysis (VNA), and Eye Diagram capture. After spending the morning on a Tektronix DSA8300 sampling oscilloscope and an Anritsu MS4647B VNA, I finally internalized how these tools complement each other. TDR tells you *where* an impedance discontinuity lives, VNA tells you *how much* it attenuates and reflects across frequency, and the eye diagram tells you *whether your system can actually open its eyes* at the receiver. These three measurements form the verification trifecta for any serial link from PCIe Gen5 to 100G Ethernet.

## The Core Concept

The fundamental reason we need all three is that high-speed signals are simultaneously time-domain and frequency-domain creatures. A TDR sends a fast step (typically 35-50 ps rise time) down the trace and measures reflections. Every impedance change—a via, a connector, a stub—creates a reflection whose amplitude and polarity reveal the impedance mismatch. The math is simple: reflection coefficient Γ = (Z_load - Z_0)/(Z_load + Z_0). A positive reflection means higher impedance (open-ish), negative means lower (short-ish). TDR gives you spatial resolution: you can pinpoint a discontinuity to within millimeters.

A VNA, on the other hand, sweeps a sine wave across frequency and measures S-parameters. S11 (return loss) tells you how much energy bounces back; S21 (insertion loss) tells you how much gets through. This is critical because a trace that looks fine at DC might have a resonant null at 8 GHz due to a quarter-wave stub. TDR won't show that clearly, but S21 will.

The eye diagram is the ultimate pass/fail. It's an overlay of thousands of bit transitions, triggered by a recovered clock. The "eye opening" (height and width) directly correlates to bit error rate (BER). A closed eye means your margin is gone—no amount of equalization can save a channel with 20 dB loss at Nyquist.

## Key Commands / Configuration / Code

### TDR Setup on Tektronix DSA8300 (via GPIB or SCPI)

```python
# Python script to automate TDR measurement
import pyvisa
rm = pyvisa.ResourceManager()
scope = rm.open_resource('GPIB0::1::INSTR')

# Set TDR step amplitude to 250 mV, rise time 35 ps
scope.write(':TDR:STEP:AMPL 0.25')
scope.write(':TDR:STEP:RTIME 35e-12')

# Set horizontal scale to 2 ns/div (typical for 12-inch trace)
scope.write(':HORIZONTAL:SCALE 2e-9')

# Acquire and read impedance waveform
scope.write(':ACQuire:STATE ON')
scope.query('*OPC?')
impedance_data = scope.query_ascii_values(':WAVeform:DATA?')

# Convert to ohms: Tektronix uses 8-bit signed, scale factor
# Typical: 0.5 ohm per LSB, offset 50 ohms
impedance_ohms = [50 + (val * 0.5) for val in impedance_data]
```

### VNA Calibration and S21 Measurement (Anritsu MS4647B)

```bash
# SCPI commands for 2-port calibration and measurement
# Assume cal kit is connected, set frequency sweep
:SENSe:FREQuency:STARt 10e6
:SENSe:FREQuency:STOP 20e9
:SENSe:SWEep:POINts 1601

# Perform SOLT calibration on ports 1 and 2
:CALCulate:SCORrection:COLLect:ACQuire:TYPE SHORt, OPEN, LOAD, THRU
:CALCulate:SCORrection:COLLect:SAVE

# Measure S21 (forward transmission)
:CALCulate:PARameter:DEFine 'S21', S21
:INITiate:IMMediate
:CALCulate:DATA:SDATA?  # Returns complex S21 in dB and phase
```

### Eye Diagram Capture (Keysight Infiniium, Python)

```python
# Configure eye diagram on a real-time oscilloscope
scope.write(':ACQuire:MODE RTIMe')  # Real-time mode
scope.write(':ACQuire:SRATe 80e9')  # 80 GSa/s for 10 Gbps signal
scope.write(':EYE:SOURce CHANnel1')
scope.write(':EYE:THReshold 0.0')   # Decision threshold at 0 V
scope.write(':EYE:UI 100e-12')      # Unit interval = 100 ps (10 Gbps)

# Capture 100k bits for statistical significance
scope.write(':ACQuire:COUNt 100000')
scope.write(':DIGitize')

# Read eye measurements
eye_height = scope.query(':MEASure:EYE:HEIGht?')
eye_width  = scope.query(':MEASure:EYE:WIDTh?')
jitter_pk  = scope.query(':MEASure:JITTer:PKPK?')
print(f"Eye height: {eye_height} V, Eye width: {eye_width} s, Jitter: {jitter_pk} s")
```

## Common Pitfalls & Gotchas

1. **TDR rise time mismatch**: Using a TDR with a rise time slower than your signal's edge rate will hide discontinuities. A 35 ps TDR step resolves features down to about 7 mm (assuming ε_r=4). If your signal has 20 ps edges, you need a faster TDR or you'll miss vias and stubs that cause real problems.

2. **VNA calibration drift**: Temperature changes of even 2°C after a full 2-port SOLT calibration can shift S11 by 0.5 dB at 20 GHz. Always perform a "recal" if the lab temperature changed, or use an electronic calibration (eCal) module that self-corrects. I once chased a phantom resonance for two hours—turned out the cal was stale.

3. **Eye diagram trigger jitter**: If you trigger on the data signal itself (instead of a clean clock), the jitter measurement will be inflated by the trigger's own noise. Always use a recovered clock from a CDR or a dedicated clock output. On a real-time scope, use the clock recovery PLL set to the standard's loop bandwidth (e.g., 10 MHz for PCIe Gen4).

## Try It Yourself

1. **TDR impedance profiling**: Take a 6-inch microstrip trace with a known 50 Ω design. Introduce a 10-mil stub at the midpoint (simulate a test point). Measure with TDR and note the impedance dip. Calculate the stub length from the time delay (round-trip) and compare to physical measurement.

2. **VNA insertion loss vs. frequency**: Measure S21 of a 12-inch differential pair (e.g., HDMI or USB cable). Sweep from 10 MHz to 10 GHz. Identify the 3 dB bandwidth. Then compute the loss at Nyquist for a 5 Gbps signal (2.5 GHz). Is it within the equalizer's range (typically 20-30 dB)?

3. **Eye diagram mask test**: Capture an eye diagram from a known-good PCIe Gen3 link (8 Gbps). Apply the PCIe mask (available in most scopes as a built-in standard). Measure the eye height and width. Then intentionally add a 2-inch stub on the trace and re-measure. Observe how the eye closes and which mask violations appear.

## Next Up

Tomorrow: **EMI Considerations in High-Speed Layout** — how your clean 10 Gbps channel becomes an unintentional antenna, and the layout techniques (grounded coplanar waveguide, stitching vias, and slot avoidance) that keep you out of the FCC's crosshairs.
