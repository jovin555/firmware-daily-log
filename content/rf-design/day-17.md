---
title: "Day 17: Debugging RF Issues: Detuning, Desense & Coexistence Problems"
date: 2026-07-28
tags: ["til", "rf-design", "detuning", "desense"]
---

## What I Explored Today

Today I dove into the three most common RF headaches that plague embedded systems: antenna detuning, receiver desensitization (desense), and coexistence interference. These issues are notoriously hard to reproduce because they depend on physical proximity, user interaction, and environmental noise. I spent the day building a systematic debug flow using a spectrum analyzer, a VNA, and a few custom test scripts to isolate each problem type.

## The Core Concept

RF problems in embedded systems rarely announce themselves with a clear error code. Instead, you see a dropped connection, a higher bit error rate, or a range that’s 10 meters shorter than expected. The root cause usually falls into one of three buckets:

**Detuning** happens when the antenna’s impedance changes due to nearby objects (a hand, a metal enclosure, a battery). The antenna’s resonant frequency shifts, and the return loss (S11) degrades. This is purely a passive network issue—no active circuitry is involved.

**Desense** occurs when a strong in-band or near-band interferer overloads the receiver’s LNA or mixer, pushing it into compression. The receiver can no longer hear the desired signal because the noise floor is artificially elevated. This is an active circuit problem.

**Coexistence** is a system-level problem where two radios (e.g., BLE and Wi-Fi on the same 2.4 GHz band) transmit at the same time, causing packet collisions. Even with perfect filtering, if the timing overlaps, data gets corrupted.

The key insight: you must isolate the domain (passive antenna, active receiver, or system timing) before you can fix it. Jumping to a filter solution when the problem is detuning will waste time and money.

## Key Commands / Configuration / Code

### 1. Detuning Check with a VNA (Vector Network Analyzer)

I use a NanoVNA for quick field checks. The goal is to measure S11 (return loss) of the antenna in free space vs. in the final enclosure with a hand nearby.

```bash
# Set up NanoVNA for 2.4 GHz ISM band
# Frequency range: 2.0 GHz to 2.6 GHz
# Calibrate with open/short/load at the antenna connector
# Then connect DUT (device under test)

# After calibration, capture S11 trace:
# Save to CSV for later comparison
# Command on NanoVNA (via serial terminal):
chop 0
sweep
dump
# This outputs frequency and S11 magnitude in dB
```

Expected result: In free space, S11 should be below -10 dB at 2.44 GHz. With a hand covering the antenna, it often rises to -3 dB or worse, indicating severe detuning.

### 2. Desense Detection with a Spectrum Analyzer

To detect desense, I measure the receiver’s noise floor while a potential interferer is active. I use a Siglent SSA3021X with a near-field probe.

```bash
# Spectrum analyzer settings for desense check:
# Center frequency: 2.44 GHz (BLE channel 39)
# Span: 10 MHz
# RBW: 100 kHz
# VBW: 100 kHz
# Sweep time: 100 ms

# Place near-field probe near the receiver LNA input
# First, with all transmitters OFF:
# Record noise floor (should be ~ -110 dBm)

# Then, enable the suspected aggressor (e.g., Wi-Fi on channel 6)
# If noise floor rises by >3 dB, you have desense.
```

### 3. Coexistence Packet Loss Measurement

I use a simple BLE peripheral running a throughput test. The script below runs on an nRF52840 DK and measures packet error rate (PER) with and without a Wi-Fi aggressor.

```python
# ble_throughput_test.py
# Requires nRF Connect SDK and a BLE sniffer
import time
import serial

# Configure serial to the DK
ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)

def send_command(cmd):
    ser.write((cmd + '\n').encode())
    time.sleep(0.1)
    return ser.read_all().decode()

# Start BLE peripheral advertising on channel 39 (2.48 GHz)
print(send_command("at ble advstart"))

# Start throughput test: send 1000 packets of 20 bytes
print(send_command("at ble throughput 1000 20"))

# Wait for result
time.sleep(5)
result = send_command("at ble throughput result")
print(f"Baseline PER: {result}")

# Now enable Wi-Fi on channel 6 (2.437 GHz) on a co-located module
# Repeat the test
print(send_command("at ble throughput 1000 20"))
time.sleep(5)
result = send_command("at ble throughput result")
print(f"With Wi-Fi PER: {result}")
```

Expected output: Baseline PER < 1%. With Wi-Fi active, PER may jump to 15-30% if coexistence is poor.

## Common Pitfalls & Gotchas

**1. Confusing detuning with desense.** If your RSSI drops when you touch the device, it’s probably detuning. If RSSI drops when a nearby Wi-Fi router is active, it’s desense. Always test with the antenna in free space first (use a plastic jig) to separate the two.

**2. Forgetting to calibrate the VNA after every cable movement.** A NanoVNA calibration is only valid for the exact cable and connector setup used during calibration. Moving the cable or changing adapters invalidates the trace. Recalibrate every time you change the physical setup.

**3. Assuming a filter will fix coexistence.** A SAW filter can attenuate out-of-band energy, but if the interferer is in-band (e.g., Wi-Fi channel 6 at 2.437 GHz and BLE channel 19 at 2.44 GHz), no filter will help. You need time-domain coordination (e.g., TDM, or a coexistence interface like the nRF52840’s PTA pin).

## Try It Yourself

1. **Detuning test:** Take a BLE module with a chip antenna. Measure S11 with a VNA in free air, then place your hand directly over the antenna. Note the frequency shift and S11 degradation. Try adding a 2 mm gap of plastic between the antenna and your hand—does it improve?

2. **Desense experiment:** Use a spectrum analyzer with a near-field probe. Place the probe near the LNA input of a receiver. Turn on a 2.4 GHz Wi-Fi router 1 meter away. Measure the noise floor rise. Then add a 2.4 GHz SAW filter (e.g., Murata SF2406) between the antenna and LNA. Measure again—did the noise floor drop?

3. **Coexistence measurement:** Set up two nRF52840 DKs: one as a BLE peripheral, one as a central. Run a throughput test. Then place a Wi-Fi module (e.g., ESP32) transmitting on channel 6 at full power 10 cm away. Measure the PER with and without using the PTA (Packet Traffic Arbiter) pins to coordinate transmissions.

## Next Up

Tomorrow is Day 18: **Full Review & Project: Design & Match an Antenna Front-End for a BLE Module**. We’ll take everything from the past 17 days and build a complete antenna matching network from scratch—including simulation, PCB layout, and VNA verification. Bring your calculator and your soldering iron.
