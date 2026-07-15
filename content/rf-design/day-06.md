---
title: "Day 06: S-Parameters: Understanding S11, S21 & Return Loss"
date: 2026-07-15
tags: ["til", "rf-design", "s-parameters", "return-loss"]
---

## What I Explored Today

I spent the day getting hands-on with S-parameters — specifically S11 (return loss) and S21 (insertion loss) — using a Vector Network Analyzer (VNA) to characterize a simple 2.4 GHz PCB trace antenna and a balun filter. If you’ve ever stared at a Smith chart and wondered what the numbers actually mean for your embedded system, today’s log is for you. S-parameters are the language of RF networks, and understanding them is the difference between a radio that works and one that mysteriously drops packets.

## The Core Concept

S-parameters (scattering parameters) describe how RF energy moves through a multi-port network. For embedded engineers, the two most critical are:

- **S11 (Return Loss)**: How much power is reflected back from the load (antenna, filter, etc.) versus what was sent in. A perfect match gives S11 = -∞ dB; a short or open gives S11 = 0 dB (all power reflected). In practice, we target S11 < -10 dB (≤ 10% reflected power) for decent matching.
- **S21 (Insertion Loss)**: How much power passes from port 1 to port 2. For an antenna, this is the transmitted power minus ohmic and mismatch losses. A good filter might have S21 > -1 dB in-band, and S21 < -20 dB out-of-band.

Why does this matter? Because every dB of return loss is power that never reaches the antenna — it bounces back into your PA, potentially causing distortion, desense, or even damage. And every dB of insertion loss directly reduces your link budget. You can’t fix what you don’t measure.

## Key Commands / Configuration / Code

I used a NanoVNA (a cheap but capable 2-port VNA) with a SOLT calibration kit. Here’s the exact procedure and a Python script to parse the exported S2P file.

### VNA Setup (NanoVNA)
```bash
# 1. Calibrate at the DUT reference plane
# Connect OPEN, SHORT, LOAD (50 Ω) to port 1, then THRU between port 1 and 2
# Menu: CAL -> RESET -> OPEN -> SHORT -> LOAD -> THRU -> DONE

# 2. Set frequency sweep
# Menu: STIMULUS -> START 2.4 GHz -> STOP 2.5 GHz

# 3. Save S2P file to SD card
# Menu: SAVE -> FORMAT S2P -> SAVE 0 (file name)
```

### Python Script to Plot S11 and S21
```python
import numpy as np
import matplotlib.pyplot as plt

def parse_s2p(filename):
    """Parse a standard Touchstone S2P file (RI format)."""
    with open(filename, 'r') as f:
        lines = f.readlines()
    
    # Skip header lines starting with '!', '#', or blank
    data_lines = [l for l in lines if not l.startswith('!') and not l.startswith('#') and l.strip()]
    
    freq = []
    s11_mag = []
    s21_mag = []
    
    for line in data_lines:
        parts = line.split()
        if len(parts) < 9:
            continue
        f_hz = float(parts[0])
        # RI format: S11_real S11_imag S21_real S21_imag S12_real S12_imag S22_real S22_imag
        s11 = complex(float(parts[1]), float(parts[2]))
        s21 = complex(float(parts[3]), float(parts[4]))
        
        freq.append(f_hz / 1e6)  # Convert to MHz
        s11_mag.append(20 * np.log10(abs(s11)))  # dB
        s21_mag.append(20 * np.log10(abs(s21)))  # dB
    
    return np.array(freq), np.array(s11_mag), np.array(s21_mag)

# Load data
freq, s11_db, s21_db = parse_s2p('antenna_2p4g.s2p')

# Plot
plt.figure(figsize=(10, 6))
plt.plot(freq, s11_db, label='S11 (Return Loss)', linewidth=2)
plt.plot(freq, s21_db, label='S21 (Insertion Loss)', linewidth=2)
plt.axhline(y=-10, color='gray', linestyle='--', label='-10 dB threshold')
plt.xlabel('Frequency (MHz)')
plt.ylabel('Magnitude (dB)')
plt.title('S-Parameters of 2.4 GHz PCB Antenna')
plt.legend()
plt.grid(True)
plt.show()
```

### Interpreting the Plot
- Where S11 dips below -10 dB (e.g., at 2.45 GHz), the antenna is well-matched.
- S21 should be as close to 0 dB as possible in-band. If you see S21 = -3 dB, you’ve lost half your power to losses or mismatch.
- A sharp S11 notch with narrow bandwidth means the antenna is resonant but may be sensitive to detuning.

## Common Pitfalls & Gotchas

1. **Calibration Plane Mismatch**  
   If you calibrate at the VNA ports but your DUT has a long cable and connector, the measured S11 includes the cable’s loss and phase shift. Always calibrate at the DUT’s reference plane — use a calibration kit with the same connectors as your test setup.

2. **Ignoring S21 When Tuning S11**  
   I’ve seen engineers tweak a matching network until S11 hits -30 dB, only to find S21 dropped by 2 dB because the network added loss. Always check both. A good match with high insertion loss is worse than a moderate match with low loss.

3. **Confusing Return Loss and VSWR**  
   Return Loss (dB) = -20 log10(|Γ|), VSWR = (1+|Γ|)/(1-|Γ|). A VSWR of 2:1 corresponds to about -9.5 dB return loss. Don’t mix them up in datasheets — a “VSWR < 2” spec is equivalent to “Return Loss < -9.5 dB”, which is marginal for many systems.

## Try It Yourself

1. **Measure Your Own Antenna**  
   Grab a NanoVNA or any 2-port VNA, calibrate it, and measure the S11 of a 2.4 GHz chip antenna (e.g., Johanson 2450AT18x100) on a development board. Plot the result and note the frequency where S11 is lowest. Is it within the intended band?

2. **Add a Series Inductor and Observe**  
   Insert a 2.2 nH series inductor between the VNA port and the antenna. Re-measure S11. How does the resonant frequency shift? This simulates the effect of a matching network or a long trace.

3. **Export and Parse Your Own S2P File**  
   Save a measurement as an S2P file from your VNA, then run the Python script above to plot S11 and S21. Change the frequency range to 2.0–3.0 GHz and look for spurious resonances.

## Next Up

Tomorrow, we’ll shift from characterization to selection: **Antenna Basics: Monopole, PIFA & Chip Antennas for Embedded Systems**. We’ll compare trade-offs in size, efficiency, and ground plane dependence — so you can pick the right antenna for your next BOM.
