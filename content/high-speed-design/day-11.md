---
title: "Day 11: DDR Routing: Fly-by Topology & Length Matching Rules"
date: 2026-07-20
tags: ["til", "high-speed-design", "ddr", "fly-by"]
---

## What I Explored Today

Today I dug into the physical-layer routing constraints for DDR3/DDR4 memory interfaces, specifically the fly-by topology for address/command/control signals and the accompanying length matching rules. After spending the morning with a 4-layer board layout for a dual-rank DDR4 design, I confirmed why fly-by has replaced the older T-topology for most modern designs above 800 MT/s. I also validated my length matching budget using real timing numbers from a Micron datasheet.

## The Core Concept

DDR routing topology is not just about making traces the same length—it’s about controlling signal integrity across multiple loads. In a T-topology, the address/command bus branches out from a central point to each DRAM chip. The problem? Reflections from the stub branches cause signal degradation at higher frequencies. As data rates push past 1600 MT/s, those stubs become quarter-wave resonators.

Fly-by topology solves this by daisy-chaining the DRAM devices in a single chain. The address/command/control signals travel from the controller through each DRAM in sequence, terminating at the far end with a resistor pack (VTT termination). This eliminates stubs, giving a clean impedance-controlled path. The trade-off is that each DRAM sees the command at a slightly different time—this is the “fly-by skew.” To compensate, the DQ/DQS strobe lines must be length-matched with a *de-skew* offset relative to the clock.

The key insight: you don’t match all address lines to each other perfectly. You match them *within a group* (e.g., all address lines to the same DRAM rank) and then match the DQ group to account for the fly-by delay. The total timing budget is:

- **Address/Command skew**: ±10 ps (typical for DDR4-2400)
- **DQ/DQS to CK skew**: must compensate for fly-by delay, often 100–300 ps depending on chain length

## Key Commands / Configuration / Code

Below is a practical example of setting up length matching constraints in Altium Designer (conceptually similar in Allegro or PADS). The key is to use a *relative propagation delay* constraint, not absolute lengths, because board stackup dielectric constant varies.

```python
# Pseudo-code for DDR4 fly-by length matching in a constraint manager
# Assume 4-layer stackup: FR4, Er=4.2, trace velocity ~6.5 ps/mm

# Step 1: Define the clock group (CK_t, CK_c)
# Match within ±2 ps (about 0.3 mm)
constraint_group "DDR4_CLK" {
    net "CK_t", "CK_c"
    match_delay = 2 ps  # tightest group
}

# Step 2: Define address/command group (A[0:15], BA[0:2], CAS, RAS, WE, CS, ODT, CKE)
# Match within ±10 ps (about 1.5 mm)
constraint_group "DDR4_ADD_CMD" {
    net "A*", "BA*", "CAS", "RAS", "WE", "CS*", "ODT*", "CKE*"
    match_delay = 10 ps
}

# Step 3: Define DQ/DQS groups per byte lane
# Each byte lane (DQ[0:7], DQS_t, DQS_c, DM) matched within ±2 ps
# But the *relative delay* to CK must account for fly-by skew
# For a 4-chip fly-by chain, delay per chip ~15 ps (2.3 mm)
# So Byte0 DQ group must be 45 ps longer than Byte3 DQ group
constraint_group "DDR4_BYTE0" {
    net "DQ[0:7]", "DQS0_t", "DQS0_c", "DM0"
    match_delay = 2 ps
    relative_delay = 45 ps  # longer than CK group
}

constraint_group "DDR4_BYTE3" {
    net "DQ[24:31]", "DQS3_t", "DQS3_c", "DM3"
    match_delay = 2 ps
    relative_delay = 0 ps  # shortest, closest to controller
}
```

**Real-world tip**: Use the `relative_delay` to the *clock* group, not absolute lengths. The PCB fabricator will adjust for Er tolerance. In your layout tool, set the clock as the “target” and all DQ groups as “slaves” with positive offsets.

## Common Pitfalls & Gotchas

1. **Ignoring via delay in length matching**  
   A via adds about 10–15 ps of delay per transition (top-to-bottom). If your fly-by chain snakes through vias to reach different ranks, you must account for this. I once saw a design where the address lines to the second rank had two extra vias, adding 30 ps of skew that wasn’t in the length calculation. The fix: measure via delay with a TDR or add it explicitly to your constraint.

2. **Matching DQ to CK without considering the VTT termination**  
   The fly-by chain ends at a VTT resistor pack (typically 40–60 Ω to VDDQ/2). If you place the termination too far from the last DRAM, the reflected wave causes setup/hold violations. Keep the termination within 5 mm of the last device’s pad. Also, never put a via between the last DRAM and the termination—it adds inductance.

3. **Using the same length for all DQ byte lanes**  
   This is the most common mistake. The DQ group for the DRAM closest to the controller (shortest fly-by delay) must be *shorter* than the DQ group for the farthest DRAM. If you match all DQ groups to the same length, the far DRAM’s DQ will arrive too early relative to its clock. Always compute the per-rank offset from the fly-by chain delay.

## Try It Yourself

1. **Calculate fly-by skew for a 4-chip DDR4 chain**  
   Assume each DRAM package adds 8 mm of trace between input and output. With Er=4.2, what is the total skew from chip 1 to chip 4? (Answer: ~52 ps). Then compute the required DQ offset for the farthest chip.

2. **Set up a constraint in your EDA tool**  
   Open your current DDR layout (or a reference design). Create a `match_delay` group for the address/command bus with a 10 ps tolerance. Then create a separate group for each DQ byte lane with a `relative_delay` to the clock net. Verify the tool flags any violations.

3. **Measure via delay on your test board**  
   Use a time-domain reflectometer (TDR) or a VNA to measure the delay of a single via on your board. Compare it to the theoretical value (about 10 ps per via for a 1.6 mm board). Adjust your length matching budget accordingly.

## Next Up

Tomorrow, I’ll tackle **High-Speed Serial Links: SerDes Basics (PCIe, SATA, Ethernet)** — how differential pairs, pre-emphasis, and equalization turn a lossy channel into a 16 Gbps link. We’ll look at eye diagrams and the math behind CTLE.
