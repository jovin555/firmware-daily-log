---
title: "Day 12: High-Speed Serial Links: SerDes Basics (PCIe, SATA, Ethernet)"
date: 2026-07-21
tags: ["til", "high-speed-design", "serdes", "pcie"]
---

## What I Explored Today

Today I dug into the fundamental building block of nearly every modern high-speed interface: the SerDes (Serializer/Deserializer). Whether it’s PCIe Gen5 at 32 GT/s, SATA III at 6 Gb/s, or 10GBASE-T Ethernet, they all rely on the same core SerDes architecture. I spent the morning tracing through a PCIe Gen3 link training sequence on a scope, then cross-referenced the PHY layer behavior against the PCIe Base Spec. The key insight: SerDes isn’t just about pushing bits faster—it’s about recovering a clean clock from a data stream that has no separate clock line, while compensating for channel loss that would destroy a parallel bus.

## The Core Concept

A SerDes replaces a wide, parallel bus (e.g., 32 data lines + clock) with a single differential pair (or a few lanes) running at a much higher bit rate. The magic is in the deserializer: it must recover the clock from the incoming bitstream using a CDR (Clock and Data Recovery) circuit, then align the serial bits into parallel words. This is why all modern SerDes links use **8b/10b** or **128b/130b** encoding—the encoding guarantees enough transitions (0→1 or 1→0) to keep the CDR locked, even during long runs of identical data.

The real engineering challenge is the channel. At multi-gigabit rates, the PCB trace acts as a lossy transmission line. The SerDes transmitter uses **TX equalization** (pre-emphasis/de-emphasis) to boost high frequencies, and the receiver uses **CTLE** (Continuous Time Linear Equalizer) and **DFE** (Decision Feedback Equalizer) to undo the channel’s low-pass filter effect. Without this, the eye diagram would be completely closed.

## Key Commands / Configuration / Code

When debugging a PCIe link, the first thing I do is check the link status from the OS. On Linux, `lspci` with verbose flags shows negotiated speed and width:

```bash
# Check PCIe link status (speed and width)
sudo lspci -vvv -s 01:00.0 | grep -E "LnkSta:|LnkCap:"
# Example output:
# LnkCap: Port #0, Speed 16GT/s, Width x16, ASPM L0s L1
# LnkSta: Speed 16GT/s (ok), Width x16 (ok)
```

For SATA, you can query the link speed via `smartctl`:

```bash
# Check negotiated SATA speed
sudo smartctl -l sataphy /dev/sda
# Look for "Negotiated Physical Link Speed: 6.0 Gbps"
```

On the hardware side, when configuring a SerDes in an FPGA (e.g., Xilinx GTH), the key parameters are the reference clock frequency and the encoding scheme. Here’s a snippet from a Vivado Tcl script for a PCIe Gen3 x4 core:

```tcl
# Configure GTH transceiver for PCIe Gen3 (8 GT/s)
set_property -dict [list \
    CONFIG.PCIe_Gen3 {True} \
    CONFIG.PL_Link_Cap_Max_Link_Width {X4} \
    CONFIG.PL_Link_Cap_Max_Link_Speed {8.0_GT/s} \
    CONFIG.REF_CLK_FREQ {100} \
    CONFIG.REF_CLK_SOURCE {PLL} \
] [get_ips pcie_7x_0]
```

For Ethernet, a common debug step is to check the PHY’s link status and auto-negotiation results via MDIO (Management Data Input/Output). Using `mii-tool` or `ethtool`:

```bash
# Check Ethernet PHY link and advertised speeds
sudo ethtool eth0 | grep -E "Speed|Duplex|Auto-negotiation"
# Output: Speed: 10000Mb/s, Duplex: Full, Auto-negotiation: on
```

## Common Pitfalls & Gotchas

**1. AC-coupling capacitor placement for PCIe and SATA**
Both PCIe and SATA require AC-coupling capacitors (typically 100 nF) on the TX side of each lane. A common mistake is placing them too far from the transmitter or using the wrong package size (e.g., 0402 instead of 0603), which adds parasitic inductance and degrades the signal. Always place the cap within 100 mils of the TX pin, and use a low-ESR X7R dielectric.

**2. Reference clock jitter kills the CDR**
The SerDes PLL multiplies the reference clock (e.g., 100 MHz for PCIe) up to the line rate. If that reference clock has excessive jitter (especially phase noise at the PLL loop bandwidth), the CDR cannot lock. I’ve seen boards where a cheap crystal oscillator caused link training failures at Gen3 speeds. Always use a dedicated spread-spectrum or low-jitter oscillator (e.g., SiTime SiT9120) for PCIe reference clocks.

**3. Ignoring the PCIe lane reversal and polarity inversion**
The PCIe spec allows lane reversal (logical lane 0 can be on any physical lane) and polarity inversion (P/N swapped). If your link doesn’t train, check the `Lane Reversal` and `Polarity Inversion` bits in the PCIe configuration space. Many FPGAs and ASICs handle this automatically, but if you’re designing a custom endpoint, you must ensure your SerDes supports these features.

## Try It Yourself

1. **Measure PCIe link training with a scope**: Connect a differential probe to the PCIe TX pair on your motherboard (e.g., near the GPU slot). Capture the link training sequence (Electrical Idle → Polling → Configuration → L0). Identify the TS1 and TS2 ordered sets by their 40-bit pattern. Compare the equalization coefficients (Preset hints) sent during the training.

2. **Simulate a SerDes channel in Python**: Write a simple script that generates a PRBS7 pattern, applies a lossy channel model (e.g., a 3-pole low-pass filter with 6 dB loss at Nyquist), then runs a basic CDR algorithm (bang-bang phase detector). Plot the eye diagram before and after equalization.

3. **Check your SATA link margins**: Use a SATA analyzer or an oscilloscope with SATA compliance testing software (e.g., Teledyne LeCroy SATA-Eye). Capture the eye diagram at the receiver. Measure the eye height and width. If the eye height is less than 100 mV or the width is less than 0.35 UI, your channel has too much loss—consider reducing the trace length or adding a redriver.

## Next Up

Tomorrow, I’ll tackle **Clock Distribution for High-Speed Systems: Skew & Jitter**—how to route multiple clocks to multiple SerDes lanes without introducing timing violations, and why a 100 fs RMS jitter spec can make or break your 25 Gb/s link.
