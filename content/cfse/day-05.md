---
title: "Day 05: FTA: Fault Tree Analysis - Top-Down Hazard Decomposition"
date: 2026-06-17
tags: ["til", "cfse", "fta", "fault-tree"]
---

## What I Explored Today

Today I dove into Fault Tree Analysis (FTA), the deductive, top-down method for identifying how a specific top-level hazard can occur through combinations of lower-level faults. Unlike FMEA which starts at component failures and asks "what happens?", FTA starts with the worst-case event and asks "how could this happen?". I built a fault tree for an automotive electronic parking brake (EPB) unintended application hazard, calculated minimal cut sets, and learned why this technique is non-negotiable for ASIL decomposition and safety validation.

## The Core Concept

FTA is fundamentally about **logical decomposition of failure causality**. You begin with a single, well-defined top event (e.g., "Unintended brake application at highway speed") and break it down through intermediate events until you reach basic events that represent root causes—component failures, human errors, or environmental conditions.

The power of FTA lies in its ability to reveal **dependent failures** and **common cause vulnerabilities** that FMEA often misses. When two redundant pressure sensors both fail because they share the same voltage regulator, a fault tree with shared basic events will expose that coupling. FMEA, being inductive and component-centric, typically treats each sensor failure independently.

For embedded systems, FTA serves three critical purposes:
1. **Quantitative analysis**: Compute probability of the top event from basic event failure rates
2. **Qualitative analysis**: Identify minimal cut sets—the smallest combinations of failures that cause the hazard
3. **ASIL decomposition**: Show how redundant architectures reduce single-point fault risk

The math is straightforward Boolean algebra: AND gates multiply probabilities, OR gates add them (for rare events). But the real engineering work is in defining the tree structure and assigning realistic failure rates.

## Key Commands / Configuration / Code

I used the open-source tool **OpenFTA** (command-line version) to build and analyze a fault tree. Here's the input file format for a simplified EPB unintended application tree:

```
# epb_unintended.fta
# Top event: Unintended EPB application while driving

TOP "Unintended_EPB_Apply"
OR "Faulty_Command" "Hardware_Failure"

# Faulty command subtree
GATE "Faulty_Command" OR
GATE "SW_Bug_Issues_Apply" "CAN_Spurious_Message"

GATE "SW_Bug_Issues_Apply" AND
BASIC "SW_Logic_Error" 1.0e-6
BASIC "Watchdog_Fails" 1.0e-7

GATE "CAN_Spurious_Message" OR
BASIC "CAN_Bus_Short" 1.0e-8
BASIC "ECU_Spurious_Tx" 1.0e-9

# Hardware failure subtree
GATE "Hardware_Failure" OR
GATE "Motor_Driver_Fail" "Sensor_Fail_Chain"

GATE "Motor_Driver_Fail" AND
BASIC "MOSFET_Short" 1.0e-7
BASIC "Motor_Coil_Short" 1.0e-8

GATE "Sensor_Fail_Chain" AND
BASIC "Speed_Sensor_Fail" 1.0e-6
BASIC "Brake_Pos_Sensor_Fail" 1.0e-6
```

To analyze this tree with OpenFTA:

```bash
# Run qualitative analysis to find minimal cut sets
openfta -i epb_unintended.fta -o results.txt -q

# Run quantitative analysis with mission time of 1 hour (3600 seconds)
openfta -i epb_unintended.fta -o quant_results.txt -t 3600

# Generate graphical output (SVG)
openfta -i epb_unintended.fta -g tree.svg
```

The qualitative output reveals minimal cut sets:

```
Minimal Cut Sets for Top Event: Unintended_EPB_Apply
  Cut Set 1: {SW_Logic_Error, Watchdog_Fails}
  Cut Set 2: {CAN_Bus_Short}
  Cut Set 3: {ECU_Spurious_Tx}
  Cut Set 4: {MOSFET_Short, Motor_Coil_Short}
  Cut Set 5: {Speed_Sensor_Fail, Brake_Pos_Sensor_Fail}
```

Notice that cut sets 2 and 3 are single-point failures—any one of those basic events alone causes the top event. This is a red flag for ASIL D systems. The AND-gated cut sets (1, 4, 5) require dual failures, which is the goal of redundancy.

## Common Pitfalls & Gotchas

**1. The "OR-gate everything" trap.** New practitioners often model every intermediate event as an OR gate because "anything could cause it." This produces a flat tree with hundreds of single-event cut sets, making quantitative analysis meaningless. The art of FTA is finding genuine AND relationships—where multiple conditions must coexist. If you can't find AND gates, you haven't decomposed deeply enough.

**2. Ignoring common cause failures in shared basic events.** When you reuse the same basic event (e.g., "Power_Supply_Fail") in multiple branches, the analysis correctly models the dependency. But engineers often forget to include common cause events like "EMI_Event" or "Temp_Extreme" that simultaneously affect multiple redundant channels. Always add a common cause basic event under your AND gates.

**3. Confusing FTA with FMEA scope.** FTA only analyzes one top event per tree. I've seen teams try to cram "all hazards" into a single fault tree. This creates unmanageable complexity and violates the single top-event rule. Create separate trees for each distinct hazard. For an EPB, you'd have separate trees for "Unintended Apply," "Failure to Release," and "Reduced Braking Force."

## Try It Yourself

1. **Build a two-channel fault tree**: Model a redundant brake pedal position sensor system where the top event is "Both sensors report invalid position." Use AND gates for the dual failure, but add a common cause basic event "Sensor_Power_Rail_Fail" that feeds both sensor failure branches. Compute the minimal cut sets and see how the single common cause creates a single-point failure.

2. **Quantify a real system**: Take the EPB tree above and assign realistic failure rates from the IEC 62380 or MIL-HDBK-217 handbook for each basic event. Run the quantitative analysis for a 10-year mission (87,600 hours). Calculate the probability of the top event and compare it to the ASIL D target of <10⁻⁸ failures per hour.

3. **Decompose an AND gate**: Take the cut set {Speed_Sensor_Fail, Brake_Pos_Sensor_Fail} and expand each basic event into its own subtree. For example, "Speed_Sensor_Fail" could be decomposed into "Sensor_Element_Fail" AND "Signal_Conditioning_Fail." Re-run the analysis and observe how the cut set probability changes.

## Next Up

Tomorrow I'll tackle **HAZOP: Hazard & Operability Study for Embedded Systems**—the structured, guide-word-driven technique that systematically identifies hazards by applying deviations (NO, MORE, LESS, REVERSE) to every signal and parameter in your system design. We'll walk through a full HAZOP session for a steer-by-wire system, complete with the deviation table and risk ranking matrix.
