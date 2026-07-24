---
title: "Day 15: Regulatory Certification: FCC/CE/ETSI RF Compliance Basics"
date: 2026-07-24
tags: ["til", "rf-design", "fcc", "ce", "etsi"]
---

## What I Explored Today

Today I dug into the regulatory certification landscape for wireless embedded products. Specifically, I mapped out the practical requirements for FCC (US), CE (EU), and ETSI (European Telecom Standards) compliance as they apply to sub-1 GHz ISM band devices and 2.4 GHz radios. I focused on what actually matters during board bring-up: conducted vs. radiated emissions limits, occupied bandwidth rules, and the difference between intentional radiator and modular certification paths.

## The Core Concept

Regulatory compliance isn't just paperwork—it's a set of hard RF constraints baked into your design from day one. The fundamental principle is that every intentional radiator must stay within its allocated spectrum mask and not emit spurious energy that interferes with other services. For embedded engineers, this means your transmitter's power spectral density, harmonic content, and out-of-band emissions are all legally bounded.

The three major regimes differ in philosophy. FCC Part 15 (US) is equipment-authorization based: you must test to ANSI C63.10 methods and file with the FCC. CE (EU) under RED Directive 2014/53/EU is manufacturer-declaration based: you self-certify to harmonized standards like EN 300 328 (2.4 GHz) or EN 300 220 (sub-1 GHz), but you still need a Notified Body for certain categories. ETSI provides the technical standards that CE references.

The critical metric across all three is the **emission mask**—the maximum allowed power at a given frequency offset from your carrier. For example, FCC Part 15.247 for 2.4 GHz DTS devices requires that emissions at 3 MHz offset from the band edge be at least 20 dB below the peak in-band power. CE/ETSI EN 300 328 v2.2.2 uses a similar but not identical mask.

## Key Commands / Configuration / Code

### 1. Pre-compliance spectrum analyzer setup (Keysight/Rohde & Schwarz)

```python
# Python script for automated pre-compliance sweep using PyVISA
# Assumes spectrum analyzer at GPIB0::18::INSTR
import pyvisa
import numpy as np

rm = pyvisa.ResourceManager()
sa = rm.open_resource('GPIB0::18::INSTR')

# Configure for FCC Part 15.247 band-edge measurement
sa.write('*RST')
sa.write(':FREQ:CENT 2.44e9')          # Center frequency 2.44 GHz
sa.write(':FREQ:SPAN 100e6')           # Span 100 MHz to see band edges
sa.write(':BAND 100 kHz')              # Resolution bandwidth per FCC
sa.write(':DET RMS')                   # RMS detector for average power
sa.write(':SWE:TIME 100 ms')           # Sweep time
sa.write(':TRAC:TYPE MAXH')            # Max hold trace

# Set reference level to +20 dBm
sa.write(':DISP:WIND:TRAC:Y:RLEV 20')

# Trigger single sweep
sa.write(':INIT:CONT OFF')
sa.write(':INIT:IMM')
sa.query('*OPC?')

# Read trace data
trace_data = sa.query(':TRAC:DATA? TRACE1')
trace_vals = np.array(trace_data.split(',')).astype(float)

# Check band-edge compliance (2400-2483.5 MHz)
# Find power at 2400 MHz and 2483.5 MHz
idx_low = int((2.4e9 - 2.39e9) / 1e5)  # 100 kHz per point
idx_high = int((2.4835e9 - 2.39e9) / 1e5)

power_low = trace_vals[idx_low]
power_high = trace_vals[idx_high]

# FCC requires >20 dBc at band edge
peak_power = np.max(trace_vals)
if (peak_power - power_low) < 20 or (peak_power - power_high) < 20:
    print("FAIL: Band-edge margin < 20 dBc")
else:
    print("PASS: Band-edge margin OK")
```

### 2. ETSI EN 300 328 occupied bandwidth check (using Siglent SSA3000X)

```bash
# SCPI commands for occupied bandwidth measurement
# Connect via USB or Ethernet

# Set to 2.4 GHz ISM band, 20 MHz span
:FREQ:CENT 2.441e9
:FREQ:SPAN 20e6

# Set RBW to 100 kHz (ETSI requires 100 kHz for OBW)
:BAND 100e3

# Enable occupied bandwidth measurement
:CALC:MARK:FUNC:OBW:STAT ON

# Set power percentage (99% for ETSI)
:CALC:MARK:FUNC:OBW:POW 99

# Trigger and read result
:INIT:IMM
:FETCH:OBW?
# Returns: OBW_Hz, lower_freq_Hz, upper_freq_Hz
```

### 3. Conducted emissions test setup (LISN + spectrum analyzer)

```python
# Pseudocode for conducted emissions sweep (150 kHz - 30 MHz)
# Using a Line Impedance Stabilization Network (LISN)

# Configure SA for CISPR 16-1-2 quasi-peak detector
sa.write(':DET QP')                    # Quasi-peak detector
sa.write(':BAND 9 kHz')                # CISPR bandwidth for 150k-30 MHz
sa.write(':FREQ:STAR 150e3')
sa.write(':FREQ:STOP 30e6')

# Sweep with 1 MHz step, record peaks
freqs = np.arange(150e3, 30e6, 1e6)
results = []
for f in freqs:
    sa.write(f':FREQ:CENT {f}')
    sa.write(':INIT:IMM')
    sa.query('*OPC?')
    amp = float(sa.query(':CALC:MARK:Y?'))
    results.append((f, amp))

# Compare to FCC Class B limit (47 CFR 15.107)
# Example: at 1 MHz, limit is 48 dBuV (QP)
```

## Common Pitfalls & Gotchas

1. **Assuming modular certification covers your layout.** If you buy a pre-certified radio module (e.g., ESP32-WROOM), the FCC/CE grant only covers the module as tested. Changing the antenna, moving it relative to ground planes, or adding a metal enclosure voids the certification. You must re-test the host product for radiated emissions (FCC Part 15.109) even if the module itself is certified.

2. **Confusing conducted vs. radiated limits.** Many engineers test only conducted output power (at the antenna port) and assume radiated will pass. In reality, radiated emissions from PCB traces, clock harmonics, and switching regulators often dominate. A clean conducted spectrum can still fail radiated tests by 10-20 dB due to enclosure resonance or poor shielding.

3. **Ignoring band-edge requirements for narrowband modulations.** For sub-1 GHz devices using FSK or OOK, the occupied bandwidth is small, but the emission mask still applies. A common mistake is setting the frequency deviation too high, causing the 20 dB bandwidth to exceed the allowed channel spacing (e.g., 200 kHz for 868 MHz band in EU). Always measure OBW before finalizing modulation parameters.

## Try It Yourself

1. **Pre-compliance band-edge test:** Set up your spectrum analyzer with 100 kHz RBW and RMS detector. Transmit a CW carrier at 2.440 GHz. Measure the power at 2.400 GHz and 2.4835 GHz. Calculate the attenuation relative to the peak. Does it exceed 20 dBc? If not, adjust your PA filter or reduce output power.

2. **Occupied bandwidth measurement:** Configure your radio to transmit a modulated signal (e.g., BLE advertising packets). Use the OBW measurement function on your analyzer with 99% power integration. Compare the result to the maximum allowed channel bandwidth for your band (e.g., 1 MHz for BLE, 20 MHz for Wi-Fi).

3. **Conducted emissions scan:** Build a simple LISN using a 50 µH inductor and 0.1 µF capacitor (see CISPR 16-1-2). Connect your DUT power input through the LISN. Sweep from 150 kHz to 30 MHz with a 9 kHz RBW and quasi-peak detector. Identify any peaks above the FCC Class B limit line. Common culprits: buck converter switching at 500 kHz-2 MHz, and digital clock harmonics.

## Next Up

Tomorrow: **Harmonics & Spurious Emissions: Causes & Mitigation** — We'll dive into why your 2.4 GHz transmitter is radiating at 4.8 GHz and 7.2 GHz, how to model harmonic generation in nonlinear PAs, and practical filtering strategies (LC vs. SAW vs. ceramic) to stay within the spurious emission limits of FCC 15.209 and ETSI EN 300 328.
