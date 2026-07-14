---
title: "Day 05: Differential Pairs: USB, LVDS, PCIe Routing Rules"
date: 2026-07-14
tags: ["til", "high-speed-design", "differential-pairs", "routing"]
---

## What I Explored Today

Today I dug into the practical routing rules for differential pairs across three common high-speed interfaces: USB 2.0/3.0, LVDS, and PCIe Gen3/4. While the textbooks preach "100Ω differential impedance" as a mantra, the real engineering challenge lies in maintaining that impedance through vias, connectors, and package transitions while keeping intra-pair skew under control. I spent the morning simulating stackup cross-sections in Polar Si9000 and the afternoon verifying routing on a 6-layer board that carries all three interfaces. The key takeaway: differential routing is 20% impedance calculation and 80% disciplined geometry management.

## The Core Concept

Differential signaling works because the electromagnetic fields between the P and N traces cancel each other, reducing EMI and improving common-mode noise rejection. But here's what most tutorials skip: the differential impedance (Z_diff) is not simply 2× Z_single-ended. For edge-coupled microstrip, Z_diff ≈ 2 × Z_0 × (1 - 0.48 × e^(-0.96 × s/h)), where s is the edge-to-edge spacing and h is the dielectric height. This means you cannot independently set trace width and spacing—they are coupled variables.

For USB 2.0 (480 Mbps), the tolerance is forgiving: ±15% on impedance, and intra-pair skew under 5 ps is usually fine. But PCIe Gen4 at 16 GT/s demands ±10% impedance and skew under 2 ps. LVDS sits in between, but its low swing (350 mV) makes it sensitive to any impedance discontinuity. The practical rule: always route differential pairs as a single entity—same layer, same number of vias, same length, and a constant gap between the traces. Never split a pair across layers unless you have a clear return path.

## Key Commands / Configuration / Code

### 1. Altium Designer Differential Pair Rules (for a 6-layer stackup)

```text
// Set up differential pair class for USB, LVDS, PCIe
// In PCB Rules and Constraints Editor:

// Rule: Differential Pair Routing - USB_DP/DM
Where the object matches: InNetClass('USB_Diff')
Constraints:
  Min Trace Width: 0.15mm
  Preferred Trace Width: 0.18mm
  Max Trace Width: 0.20mm
  Min Gap: 0.15mm
  Preferred Gap: 0.20mm
  Max Gap: 0.25mm
  Impedance: 90Ω ±10% (USB 2.0/3.0 uses 90Ω, not 100Ω)

// Rule: Differential Pair Routing - PCIe_TX/RX
Where the object matches: InNetClass('PCIe_Diff')
Constraints:
  Min Trace Width: 0.12mm
  Preferred Trace Width: 0.15mm
  Max Trace Width: 0.18mm
  Min Gap: 0.10mm
  Preferred Gap: 0.15mm
  Max Gap: 0.20mm
  Impedance: 85Ω ±10% (PCIe Gen3/4 standard)
```

### 2. KiCad Differential Pair Setup (via PCB Editor)

```python
# In KiCad's Python console or via pcbnew API:
import pcbnew

board = pcbnew.GetBoard()

# Create differential pair for LVDS
diff_pair = pcbnew.DIFF_PAIR()
diff_pair.SetNetClass("LVDS")
diff_pair.SetWidth(0.2)      # trace width in mm
diff_pair.SetGap(0.15)       # gap in mm
diff_pair.SetViaGap(0.25)    # via gap for differential vias

# Apply to net pair
net_p = board.FindNet("LVDS_P")
net_n = board.FindNet("LVDS_N")
diff_pair.SetNet(net_p, net_n)
board.Add(diff_pair)
```

### 3. Polar Si9000 Field Solver Input (for verification)

```text
Structure: Edge-Coupled Microstrip
Dielectric: FR-4 (Er = 4.2 @ 1GHz)
Height to ground: 0.1mm (prepreg)
Trace width: 0.15mm
Trace spacing: 0.15mm
Copper thickness: 0.035mm (1oz)
Target Z_diff: 100Ω ±10%

Result: Z_diff = 98.3Ω (within tolerance)
```

## Common Pitfalls & Gotchas

**1. The "100Ω for everything" trap.** USB 2.0/3.0 actually specifies 90Ω differential impedance, not 100Ω. PCIe Gen3/4 uses 85Ω. Only LVDS and Ethernet typically use 100Ω. Using a 100Ω stackup for USB will cause reflections at the connector. Always check the specific interface standard—the USB 2.0 spec (section 7.1.3) clearly states 90Ω ±15%.

**2. Routing differential pairs through BGA fanout without proper anti-pad clearance.** When you transition a differential pair through a via field, the antipads must be large enough to maintain the impedance. A common mistake is using standard 0.3mm antipads for 0.2mm vias—this drops the impedance by 10-15Ω. For PCIe, I use 0.5mm antipads with 0.25mm vias and keep the ground plane clearance at least 0.2mm from the via barrel.

**3. Ignoring the return current path at layer transitions.** When a differential pair switches layers, the return current must also switch reference planes. If you don't place stitching vias within 1mm of the signal vias, the return current takes a longer path, creating a loop antenna. For high-speed pairs, I always place a GND via within 0.5mm of each signal via in the pair.

## Try It Yourself

**Task 1: Stackup calculation.** Using Polar Si9000 or your preferred field solver, design a 4-layer stackup for USB 2.0 (90Ω differential). Start with 0.2mm trace width, 0.2mm gap, and 0.1mm prepreg to ground. Adjust the trace width until you hit 90Ω ±5%. Record the final width and gap.

**Task 2: Skew measurement.** In your EDA tool, route a 100mm differential pair for LVDS. Then intentionally add 5mm extra length to the P trace. Run a time-domain reflectometry (TDR) simulation and measure the skew at the receiver. How much does the eye diagram degrade?

**Task 3: Via optimization.** Create a differential via pair for PCIe Gen4. Start with 0.3mm vias and 0.4mm antipads. Simulate the impedance through the via transition. Then reduce the antipad to 0.3mm and observe the impedance dip. Add two GND stitching vias and re-simulate. Document the impedance change.

## Next Up

Tomorrow I'll tackle **Length Matching & Skew Budget Analysis**—specifically how to calculate the allowable skew for USB 3.0 SuperSpeed (5 Gbps) versus PCIe Gen4 (16 GT/s), and why a 1mm length mismatch can kill your link budget. We'll walk through real skew budgets from the PCIe Base Spec and build a spreadsheet to track it across a 12-inch trace.
