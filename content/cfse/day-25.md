---
title: "Day 25: FTA: Fault Tree Analysis - Top-Down Hazard Decomposition"
date: 2026-07-07
tags: ["til", "cfse", "fta", "fault-tree"]
---

## What I Explored Today

Today I dug into Fault Tree Analysis (FTA), the top-down deductive method for decomposing a system-level hazard into its root causes. Unlike FMEA which asks "what happens if this component fails?", FTA starts with the worst-case event and asks "what combination of failures leads here?" I worked through building fault trees for a steer-by-wire system, using both qualitative cut-set analysis and quantitative probability calculations. The key insight: FTA forces you to think in Boolean logic about failure propagation, which is exactly what you need when arguing that your safety mechanism actually prevents the hazard.

## The Core Concept

FTA is the hammer you pull out when you need to prove *why* a hazard cannot occur, or to find the minimal set of failures that must be prevented. The top event is your hazard (e.g., "Unintended steering to full lock"). You then decompose downward through intermediate events using two gates:

- **OR gate**: any single input causes the output (failure is additive)
- **AND gate**: all inputs must occur simultaneously for the output (failure is multiplicative)

The power of FTA is in the *cut sets* — the minimal combinations of basic events that cause the top event. A single-point failure (a cut set of size 1) is a red flag. A cut set requiring three simultaneous failures (size 3) is much more tolerable. For ASIL-D systems, you typically need no single-point failures and double-point failures must be covered by diagnostic coverage.

Quantitatively, if you assign failure rates (λ) to basic events, you can compute the top event probability using Boolean algebra. For an OR gate with independent events: P(top) ≈ Σ P(basic_i). For AND: P(top) ≈ Π P(basic_i). This lets you check against your safety goal's probabilistic metric (e.g., PMHF < 10⁻⁹ failures/hour for ASIL-D).

## Key Commands / Configuration / Code

I used the open-source tool **OpenFTA** for this analysis, but the XML format is portable. Here's a fragment of a fault tree for unintended steering lock:

```xml
<!-- fault_tree.xml - Steer-by-wire unintended full lock -->
<fault-tree name="SteerByWire_UnintendedLock">
  <!-- Top event: Hazard -->
  <event id="TOP" name="Unintended steering to full lock" />
  
  <!-- OR gate: either command or mechanical failure -->
  <gate id="G1" type="OR">
    <inputs>
      <event ref="E1" />  <!-- Spurious motor command -->
      <event ref="E2" />  <!-- Mechanical jam to lock -->
    </inputs>
  </gate>
  
  <!-- AND gate: both ECUs must fail for spurious command -->
  <gate id="G2" type="AND">
    <inputs>
      <event ref="E3" />  <!-- Primary ECU fails high -->
      <event ref="E4" />  <!-- Secondary ECU fails high -->
    </inputs>
  </gate>
  
  <!-- Basic events with failure rates (per hour) -->
  <basic-event id="E3" name="Primary ECU - output stuck high" 
               probability="1.0e-7" />
  <basic-event id="E4" name="Secondary ECU - output stuck high" 
               probability="1.0e-7" />
  <basic-event id="E1" name="Spurious motor command" 
               probability="1.0e-14" />  <!-- AND of E3 & E4 -->
  <basic-event id="E2" name="Mechanical jam to lock" 
               probability="1.0e-9" />
</fault-tree>
```

To compute minimal cut sets and top event probability:

```bash
# Using OpenFTA CLI (openfta v2.3)
openfta --input fault_tree.xml --cut-sets --minimal --output cuts.txt

# Output: Minimal cut sets
# Cut set 1: {Mechanical jam to lock}  -- single point failure!
# Cut set 2: {Primary ECU fails high, Secondary ECU fails high}

# Calculate top event probability
openfta --input fault_tree.xml --probability --output prob.txt
# Top event probability: 1.0e-9 + 1.0e-14 ≈ 1.0e-9 failures/hour
```

The cut-set output immediately shows the problem: a mechanical jam is a single-point failure. This forces a design change — add a mechanical stop or redundant steering path.

For quantitative analysis with dependent failures (common cause), I used the beta-factor model:

```python
# common_cause.py - Beta factor model for dual-ECU
lambda_primary = 1e-7  # per hour
lambda_secondary = 1e-7
beta = 0.02  # 2% common cause factor (typical for diverse ECUs)

# Independent failure rate
lambda_ind = (1 - beta) * lambda_primary  # 9.8e-8

# Common cause failure rate (both fail together)
lambda_cc = beta * lambda_primary  # 2.0e-9

# Effective AND-gate probability (with CCF)
P_AND = (lambda_ind * lambda_ind * exposure_time) + (lambda_cc * exposure_time)
# For exposure_time = 1 hour: P_AND ≈ 2.0e-9 (dominated by CCF!)
```

## Common Pitfalls & Gotchas

1. **Ignoring common cause failures (CCF) in AND gates**: I see this constantly. Engineers model a dual-redundant system with an AND gate and claim the probability is λ². But if both ECUs share a power supply that fails, or both run the same software with the same bug, the actual probability is λ_CCF, which can be 1000x higher. Always apply a beta factor (β = 0.01–0.10) for dependent failures.

2. **OR gates with non-independent events**: FTA assumes events are independent unless you explicitly model dependencies. If two basic events both depend on the same sensor, you need to add that sensor failure as a separate event feeding both. Otherwise, your cut sets will be misleadingly small.

3. **Confusing "failure" with "fault"**: A basic event should be a component failure mode (e.g., "resistor opens"), not a system fault (e.g., "no output"). The tree decomposes faults into failures. If you stop at "ECU fails", you haven't gone deep enough — what exactly fails inside the ECU? The tree must reach the component level where you have actual failure rate data.

## Try It Yourself

1. **Build a fault tree for an airbag deployment hazard**: Top event = "Unintended airbag deployment while driving". Decompose through the sensor, ECU, and squib driver. Identify at least one AND gate (dual sensor voting) and one OR gate (multiple failure paths). Compute the minimal cut sets.

2. **Add common cause failure to your tree**: Take the dual-ECU example above and add a "Shared power supply fails" basic event that feeds both E3 and E4. Recompute the cut sets. How does the top event probability change? (Hint: you'll get a new single-point failure.)

3. **Quantitative comparison**: For a hazard with a safety goal of PMHF < 10⁻⁸ failures/hour, calculate whether your airbag tree meets the target. If not, identify which cut set dominates and propose a design change (e.g., add a mechanical safing sensor).

## Next Up

Tomorrow: **HAZOP: Hazard & Operability Study for Embedded Systems** — the structured brainstorming technique that uses guide words (NO, MORE, LESS, REVERSE) to systematically probe every signal and function in your system for deviations. We'll walk through a HAZOP worksheet for a brake-by-wire controller and compare it with FTA and FMEA.
