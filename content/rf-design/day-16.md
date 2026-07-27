---
title: "Day 16: Harmonics & Spurious Emissions: Causes & Mitigation"
date: 2026-07-27
tags: ["til", "rf-design", "harmonics", "spurious-emissions"]
---

## What I Explored Today

Today I dug into the practical side of harmonics and spurious emissions—not just the theory, but what actually causes them in real embedded designs and how to fix them before your product fails FCC/ETSI radiated emissions testing. I focused on three common culprits: PA nonlinearity, clock harmonics coupling into RF paths, and switching regulator noise. I also validated mitigation strategies using a spectrum analyzer and a near-field probe set.

## The Core Concept

Harmonics are integer multiples of your fundamental carrier frequency. A 2.4 GHz transmitter at 10 dBm will produce energy at 4.8 GHz (2nd harmonic), 7.2 GHz (3rd harmonic), and so on. Spurious emissions are *non-harmonic* tones—they can come from mixing products, digital clock leakage, or PLL reference spurs.

The root cause is almost always **nonlinearity**. In an ideal linear amplifier, output is a scaled copy of the input. Real PAs have a transfer function that can be modeled as a power series:

`Vout = a1*Vin + a2*Vin^2 + a3*Vin^3 + ...`

The squared term (a2) produces second harmonics and intermodulation products. The cubed term (a3) produces third harmonics and is the dominant source of adjacent-channel interference. The key insight: **every dB of output power compression increases harmonic levels by roughly 2 dB** for second harmonics and 3 dB for third harmonics.

For spurious emissions, the mechanism is different. A 32.768 kHz RTC clock on a PCB trace running parallel to your RF output line will capacitively couple its harmonics (especially the 3rd at ~98 kHz, but more critically the 10th+ at MHz frequencies) directly into the antenna feed. Similarly, a buck converter switching at 2.2 MHz can produce spurs at multiples of that frequency that land inside your receive band.

## Key Commands / Configuration / Code

### 1. Spectrum Analyzer Harmonic Sweep (Keysight / Siglent)

```python
# Pseudo-code for automated harmonic measurement using PyVISA
import pyvisa
rm = pyvisa.ResourceManager()
sa = rm.open_resource('TCPIP0::192.168.1.100::inst0::INSTR')

# Configure for fundamental at 2.45 GHz
sa.write(':FREQ:CENTER 2.45 GHz')
sa.write(':FREQ:SPAN 100 MHz')
sa.write(':BAND 1 MHz')
sa.write(':DISP:TRACE:Y:RLEV 20 dBm')

# Measure fundamental power
fund_power = float(sa.query(':CALC:MARK1:Y?'))
print(f"Fundamental: {fund_power:.1f} dBm")

# Sweep harmonics: set center to 2*f0, 3*f0, etc.
for n in range(2, 6):
    center_freq = n * 2.45e9
    sa.write(f':FREQ:CENTER {center_freq} Hz')
    sa.write(':FREQ:SPAN 200 MHz')
    sa.write(':BAND 3 MHz')  # wider RBW for harmonics
    harm_power = float(sa.query(':CALC:MARK1:Y?'))
    print(f"{n}th harmonic @ {center_freq/1e9:.2f} GHz: {harm_power:.1f} dBm")
    # FCC 15.247 limit: -20 dBc or less for harmonics
    if (harm_power - fund_power) > -20:
        print("  FAIL: Harmonic exceeds -20 dBc limit")
```

### 2. Near-Field Probe Scan for Spurious Sources

```bash
# Using a TEM-cell or near-field H-probe with a spectrum analyzer
# Set analyzer to max hold, sweep from 30 MHz to 10 GHz
# Common spurious frequencies to check:
# - 32.768 kHz * N (RTC harmonics)
# - 2.2 MHz * N (buck converter)
# - 25 MHz * N (Ethernet PHY clock)
# - 48 kHz * N (USB full-speed)

# On the analyzer (SCPI commands):
:FREQ:STAR 30 MHz
:FREQ:STOP 10 GHz
:DISP:TRACE:Y:RLEV -20 dBm
:TRIG:SOUR EXT  # Use external trigger from DUT TX burst
```

### 3. Pi Filter Design for PA Output (LTSpice netlist)

```spice
* 2.45 GHz harmonic filter - 3rd order lowpass
* Cutoff: 3.0 GHz, Impedance: 50 ohms
* Values from standard EIA capacitor/inductor series

V1 PA_OUT 0 DC 0 AC 1
* Series inductor (3.3 nH, Coilcraft 0402CS)
L1 PA_OUT N001 3.3n
* Shunt capacitor (1.0 pF, Murata GJM15)
C1 N001 0 1.0p
* Series inductor (3.3 nH)
L2 N001 N002 3.3n
* Shunt capacitor (1.0 pF)
C2 N002 0 1.0p
* Load
Rload N002 0 50

.ac dec 100 100MHz 10GHz
.plot ac V(N002)
```

## Common Pitfalls & Gotchas

**1. The "20 dBc" trap.** Many engineers think FCC Part 15.247 requires harmonics to be 20 dB *below the fundamental*. It actually requires them to be 20 dB *below the highest in-band emission level*, which is often the fundamental but could be a modulation sideband. Always measure the peak in-band power, not just the carrier.

**2. Harmonic cancellation from PCB layout.** A poorly placed ground via in the PA output matching network can create an unintended quarter-wave stub at the second harmonic frequency. At 2.45 GHz, a 15 mm stub (λ/4 for the 2nd harmonic at 4.9 GHz) will look like a short circuit, killing your output power. Always verify matching network layout with an EM simulator.

**3. The "quiet" switching regulator that isn't.** A buck converter running at 2.2 MHz may have its 10th harmonic at 22 MHz—far from your 2.4 GHz band, right? Wrong. The *envelope* of the switching noise can mix with the RF carrier in the PA, producing spurs at `f_carrier ± N*f_sw`. If your switching frequency is 2.2 MHz and your channel spacing is 5 MHz, the 3rd harmonic of the switcher (6.6 MHz) will create spurs at 2.45 GHz ± 6.6 MHz—right inside your adjacent channel.

## Try It Yourself

1. **Measure your PA's harmonic content.** Set your spectrum analyzer to sweep from 30 MHz to 10 GHz with max hold. Transmit a CW tone at your operating frequency. Identify all harmonics up to the 5th. Are any within 20 dBc of the fundamental? If so, add a low-pass filter with cutoff at 1.5× your fundamental frequency and re-measure.

2. **Find your clock spurs.** Use a near-field H-probe connected to your spectrum analyzer. Scan over your PCB while the system is in receive mode (TX off). Identify any spurs that are not integer multiples of your RF carrier. Cross-reference these frequencies with your system clocks (MCU, RTC, Ethernet, USB). Calculate which clock harmonic is causing each spur.

3. **Design and simulate a harmonic filter.** Using LTSpice or QUCS, design a 5th-order Chebyshev low-pass filter for your operating frequency with 0.5 dB ripple and cutoff at 1.3× your fundamental. Simulate the insertion loss at the fundamental and rejection at the 2nd and 3rd harmonics. Build it on a scrap PCB and measure the real-world performance.

## Next Up

Tomorrow: **Debugging RF Issues: Detuning, Desense & Coexistence Problems** — We'll walk through real-world scenarios where your antenna impedance shifts when you put the device in a plastic enclosure, or your Wi-Fi receiver desenses when the BLE transmitter fires. I'll share the systematic debug flow I use, from VNA measurements to over-the-air desense testing.
