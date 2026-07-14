---
title: "Day 14: Cellular IoT: NB-IoT vs LTE-M Tradeoffs for Battery-Powered Devices"
date: 2026-07-14
tags: ["til", "wireless-protocols", "nb-iot", "lte-m"]
---

## What I Explored Today

Today I dug into the practical tradeoffs between NB-IoT and LTE-M for battery-powered cellular IoT devices. Both are 3GPP Release 13 LPWAN technologies, but they optimize for fundamentally different use cases. I focused on real-world power consumption data, coverage class behavior, and how each protocol handles mobility—critical for deciding which to spec in a battery-constrained design.

## The Core Concept

The fundamental difference between NB-IoT and LTE-M isn't just bandwidth—it's about how they trade off latency, throughput, mobility, and power consumption. LTE-M (eMTC) supports 1.4 MHz bandwidth, up to 1 Mbps downlink, and handover between cells. NB-IoT uses 200 kHz, tops out at ~250 kbps, and does not support handover (only cell reselection). For battery life, the key is how each protocol handles the device's active time on the radio.

NB-IoT achieves lower peak current during transmission because it uses a narrower bandwidth and simpler modulation (BPSK/QPSK vs 16QAM in LTE-M). However, NB-IoT's longer transmission times (due to lower data rate) can offset this advantage. The real battery-life differentiator comes from how each protocol supports extended DRX (eDRX) and Power Saving Mode (PSM)—both of which I'll cover tomorrow.

For stationary sensors (water meters, parking sensors), NB-IoT often wins on cost and power. For mobile or latency-sensitive applications (asset trackers, wearables), LTE-M's handover and lower latency (10-15ms vs 1.6-10s for NB-IoT) are non-negotiable.

## Key Commands / Configuration / Code

When selecting a module, you'll configure the radio access technology (RAT) explicitly. Here's a practical example using an AT command set common to u-blox SARA-R4 and Quectel BG96 modules.

**Selecting LTE-M only (Cat-M1):**
```c
// Force module to LTE-M (Cat-M1) only
AT+CFUN=0                    // Deactivate RF first
AT+URAT=7                    // Set RAT to LTE-M (value varies by module)
AT+CFUN=1                    // Reactivate RF
// Verify selected RAT
AT+URAT?                     // Should return +URAT: 7
```

**Selecting NB-IoT only:**
```c
// Force module to NB-IoT only
AT+CFUN=0
AT+URAT=8                    // Set RAT to NB-IoT (value varies)
AT+CFUN=1
// Check current RAT
AT+URAT?
```

**Configuring coverage enhancement (CE) level for NB-IoT:**
```c
// NB-IoT has three coverage enhancement levels (0, 1, 2)
// CE Level 2 = deepest coverage, longest transmission time
AT+NCONFIG=AUTOCONNECT,TRUE
AT+NCONFIG=CR_0354_0338_SCRAMBLING,TRUE
AT+NCONFIG=CR_0859_SI_AVOID,TRUE
AT+CFUN=0
AT+CGDCONT=1,"IP","your.apn"
AT+CFUN=1
// After attach, check CE level
AT+CSCON?                    // Shows RRC state
AT+CEDRXS?                   // Shows eDRX parameters
```

**Measuring actual power consumption during a data send (pseudo-code for a current probe):**
```python
# Using a Nordic PPK2 or similar current profiler
import time
import serial

def measure_tx_current(serial_port, payload_size=100):
    ser = serial.Serial(serial_port, 115200)
    # Start current measurement (external tool)
    ser.write(b'AT+NSOST=0,"192.168.1.1",1234,%d,"%s"\r\n' % 
              (payload_size, 'A' * payload_size))
    time.sleep(10)  # Wait for TX completion
    # Read back current profile from measurement tool
    # Typical NB-IoT: 120-200 mA peak, 2-5 sec TX
    # Typical LTE-M: 200-400 mA peak, 0.5-1.5 sec TX
```

## Common Pitfalls & Gotchas

**1. Coverage Class Misconfiguration**
NB-IoT's Coverage Enhancement (CE) levels dramatically affect battery life. At CE Level 2 (deepest indoor), a 100-byte uplink can take 5-10 seconds of continuous TX. I've seen designs where engineers assumed 200-byte packets would take 1 second, but the module was stuck in CE Level 2, drawing 150 mA for 8 seconds per transmission. Always measure the actual CE level your device lands on in the deployment environment.

**2. Mobility Assumptions**
NB-IoT does not support handover—only cell reselection. If your device moves between cells (even slowly, like a parked car in a garage), it will experience a 10-30 second interruption while it re-attaches. LTE-M handles this seamlessly. I've debugged a "battery drain" issue where an NB-IoT tracker was re-attaching every 5 minutes, burning 10x the expected power.

**3. PSM and eDRX Interaction with RAT**
PSM and eDRX parameters are network-configured, not device-configured. The network may reject your requested eDRX cycle if it's not supported on that RAT. NB-IoT typically supports longer eDRX cycles (up to ~3 hours) than LTE-M (up to ~40 minutes). If you request a 2-hour eDRX on LTE-M, the network will silently fall back to a shorter cycle, and your device will wake more often than expected.

## Try It Yourself

1. **Power profile comparison**: Using a current probe (or a simple shunt resistor + oscilloscope), measure the TX current and duration for a 100-byte UDP packet on both NB-IoT and LTE-M. Calculate the energy per transmission (mAh). You'll likely find NB-IoT wins for small, infrequent packets, but LTE-M wins for larger payloads.

2. **Coverage class test**: Place an NB-IoT module in a metal enclosure or basement. Use `AT+NUESTATS` (or equivalent) to read the current CE level and RSSI. Send 10 packets and log the TX duration. Compare the same test with the module near a window. The difference in TX time (and thus battery drain) can be 5-10x.

3. **Mobility stress test**: Mount an LTE-M and NB-IoT module on a slow-moving robot or cart. Drive it between two cell towers while sending periodic location updates. Log connection drops and re-attach times. LTE-M should maintain the connection; NB-IoT will drop and reconnect, costing extra power.

## Next Up

Tomorrow, I'll dive into **PSM & eDRX: Cellular Power-Saving Modes Explained**—how to configure these modes to achieve multi-year battery life, and why your network operator might silently override your settings.
