---
title: "Day 14: RF Measurement: Spectrum Analyzers & VNA Calibration"
date: 2026-07-23
tags: ["til", "rf-design", "spectrum-analyzer", "vna"]
---

## What I Explored Today

Today I dug into the two most critical instruments in any RF lab—the spectrum analyzer (SA) and the vector network analyzer (VNA)—and focused specifically on what separates a measurement from a *correct* measurement: calibration. I’ve used these tools for years, but I realized I was often trusting default settings and skipping full calibrations to save time. That stops today. I explored the theory behind SA amplitude accuracy (RBW, VBW, reference level) and VNA error correction (OSL, SOLT, TRL), then ran through the actual calibration routines on a Keysight N9320B SA and a Copper Mountain TR1300/1 VNA. The difference between a raw measurement and a calibrated one is night and day—literally 10–20 dB of error in some cases.

## The Core Concept

Why can’t you just plug in a cable and read the screen? Because every instrument, cable, adapter, and fixture adds its own amplitude and phase errors. A spectrum analyzer’s input mixer, IF filters, and detector have non-flat frequency response and logarithmic compression. A VNA’s directional couplers have finite directivity, and its receivers have frequency-dependent gain and phase shift.

**Calibration is the process of measuring these systematic errors and mathematically removing them from subsequent measurements.** For an SA, this usually means a simple amplitude calibration using a known reference source (often a built-in 50 MHz, –20 dBm calibrator). For a VNA, it’s more involved: you measure known standards (Open, Short, Load, Thru) to solve for the error terms in a 12-term error model. Without this, your S-parameters are just guesses.

The key insight: calibration does not fix random noise or drift—it only removes repeatable systematic errors. That’s why you still need proper averaging, sweep time, and temperature stabilization.

## Key Commands / Configuration / Code

### Spectrum Analyzer: Amplitude Calibration (Keysight N9320B)

```python
# SCPI commands for SA calibration (via PyVISA)
import pyvisa
rm = pyvisa.ResourceManager()
sa = rm.open_resource('TCPIP0::192.168.1.100::inst0::INSTR')

# Set reference level to -20 dBm (match calibrator output)
sa.write(':DISPlay:WINDow:TRACe:Y:RLEVel -20 dBm')
# Set center frequency to 50 MHz (calibrator frequency)
sa.write(':SENSe:FREQuency:CENTer 50 MHz')
# Set span to zero (zero span for CW measurement)
sa.write(':SENSe:FREQuency:SPAN 0 Hz')
# Set RBW to 10 kHz (typical for calibrator)
sa.write(':SENSe:BANDwidth:RESolution 10 kHz')
# Enable internal calibrator (if available)
sa.write(':CALibration:RF:STATe ON')
# Perform amplitude calibration
sa.write(':CALibration:RF:AMPLitude')
# Query calibration status
status = sa.query(':CALibration:RF:STATe?')
print(f"Calibration state: {status}")
# Disable calibrator after calibration
sa.write(':CALibration:RF:STATe OFF')
```

### VNA: Full 2-Port SOLT Calibration (Copper Mountain TR1300/1)

```python
# SCPI commands for 2-port SOLT calibration
import pyvisa
rm = pyvisa.ResourceManager()
vna = rm.open_resource('TCPIP0::192.168.1.200::inst0::INSTR')

# Set frequency range: 1 MHz to 6 GHz
vna.write(':SENSe:FREQuency:STARt 1 MHz')
vna.write(':SENSe:FREQuency:STOP 6 GHz')
# Set number of points to 201
vna.write(':SENSe:SWEep:POINts 201')
# Set IF bandwidth to 1 kHz
vna.write(':SENSe:BANDwidth 1000')
# Select calibration kit (user-defined or standard)
vna.write(':SENSe:CORRection:COLLect:KIT "3.5mm"')
# Start calibration: measure Open on port 1
vna.write(':SENSe:CORRection:COLLect:PORT1:OPEN')
# Measure Short on port 1
vna.write(':SENSe:CORRection:COLLect:PORT1:SHORt')
# Measure Load on port 1
vna.write(':SENSe:CORRection:COLLect:PORT1:LOAD')
# Repeat for port 2
vna.write(':SENSe:CORRection:COLLect:PORT2:OPEN')
vna.write(':SENSe:CORRection:COLLect:PORT2:SHORt')
vna.write(':SENSe:CORRection:COLLect:PORT2:LOAD')
# Measure Thru (connect port 1 to port 2)
vna.write(':SENSe:CORRection:COLLect:THRU')
# Apply calibration
vna.write(':SENSe:CORRection:COLLect:SAVE')
vna.write(':SENSe:CORRection:STATe ON')
# Verify calibration with a known device (e.g., 50 ohm load)
vna.write(':SENSe:CORRection:COLLect:VERify')
```

### VNA: Manual Calibration Verification (Python)

```python
# After calibration, measure a 50 ohm load and check S11
vna.write(':SENSe:CORRection:STATe ON')
vna.write(':CALCulate:PARameter:DEF "S11"')
vna.write(':INITiate:CONTinuous OFF')
vna.write(':INITiate:IMMediate')
data = vna.query_ascii_values(':CALCulate:DATA:SDATA?')
# data is interleaved I/Q (real, imag) — convert to dB
import numpy as np
real = data[0::2]
imag = data[1::2]
mag = 20 * np.log10(np.sqrt(np.array(real)**2 + np.array(imag)**2))
print(f"Mean S11 magnitude: {np.mean(mag):.2f} dB")
# Should be < -40 dB across band
```

## Common Pitfalls & Gotchas

1. **Using the wrong calibration kit definition.** Every connector type (SMA, 3.5 mm, N-type, BNC) has different open capacitance, short inductance, and delay. If you select “SMA” but your cables are 3.5 mm, your calibration will be wrong above 10 GHz. Always verify the cal kit model number matches your physical standards.

2. **Forgetting to torque connectors to the correct spec.** A loose connection introduces repeatable but incorrect data. Use a torque wrench (8 in-lb for SMA/3.5 mm, 12 in-lb for N-type). I once spent two hours chasing a 0.5 dB ripple that vanished after torquing.

3. **Calibrating at the wrong temperature.** VNA error terms drift with temperature. Calibrate at the same temperature you’ll measure. If your lab varies by more than ±2°C, consider a daily re-calibration. Some modern VNAs have temperature sensors and can apply drift correction, but don’t rely on it blindly.

## Try It Yourself

1. **SA amplitude accuracy check:** Set your SA to zero span at 50 MHz, reference level –20 dBm, RBW 10 kHz. Connect the internal calibrator (or a known –20 dBm source). Measure the amplitude. Then change the reference level to –10 dBm and re-measure. How much does the reading change? (It should be < 0.1 dB if calibrated.)

2. **VNA calibration comparison:** Perform a full 2-port SOLT calibration on your VNA. After calibration, measure a 50 ohm load on port 1. Record S11 magnitude at 1 GHz, 3 GHz, and 6 GHz. Now disable calibration (set CORRection:STATe OFF) and re-measure. What’s the difference? (Expect > 20 dB improvement.)

3. **Cable phase stability test:** Calibrate your VNA with a high-quality phase-stable cable. Then flex the cable near the connector and measure S11 of a short. How much does the phase change? (A good cable should show < 1° change; a bad cable can show 10° or more.)

## Next Up

Tomorrow: **Regulatory Certification: FCC/CE/ETSI RF Compliance Basics** — we’ll break down the test setups, emission limits, and radiated vs. conducted measurements you need to pass certification on your first try.
