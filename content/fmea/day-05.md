---
title: "Day 05: Failure Chain: Failure Mode, Effect & Cause Relationships"
date: 2026-07-14
tags: ["til", "fmea", "failure-mode", "failure-chain"]
---

## What I Explored Today

Today I dug into the structural backbone of any FMEA: the failure chain. It’s the logical sequence that connects a root cause to a failure mode and then to its effect on the system or customer. Without this chain, you’re just listing problems. With it, you build a traceable map that guides design decisions, test coverage, and risk mitigation. I worked through a real example from a motor controller’s gate-driver circuit and saw how mislabeling a cause as an effect (or vice versa) can cascade into a useless FMEA.

## The Core Concept

The failure chain is a three-link sequence: **Cause → Failure Mode → Effect**. Each link answers a specific question:

- **Failure Mode**: *How does the item fail to meet its function?* This is the observable deviation at the level you’re analyzing (component, subsystem, or system).
- **Effect**: *What happens to the next higher level or the end user?* This is the consequence of the failure mode.
- **Cause**: *Why does the failure mode occur?* This is the root mechanism—physical, chemical, electrical, or human.

Why does this ordering matter? Because it forces you to think in terms of causality, not just symptoms. A common mistake is to write “overheating” as a failure mode when it’s actually an effect of excessive current (cause) that leads to a short circuit (failure mode). The chain keeps your analysis honest and actionable.

In practice, you build the chain top-down (effect → failure mode → cause) or bottom-up (cause → failure mode → effect). Most teams start with the failure mode because it’s the most visible, then trace up to effects and down to causes. The key is that every link must be a single, specific statement—no compound sentences.

## Key Commands / Configuration / Code

I use a structured spreadsheet or a YAML-based FMEA tool. Here’s a real snippet from a motor controller DFMEA I’m building. The failure chain is encoded in a three-column layout, but I also export to YAML for version control.

```yaml
# motor_controller_dfmea.yaml
# Failure chain for gate-driver IC (U1)
# Each entry is one failure mode with its cause and effect

- function: "Drive MOSFET gate with 12V ± 10% at 100 kHz"
  failure_mode: "Gate voltage falls below 10.8V during switching transient"
  effect: "MOSFET operates in linear region, increased Rds(on), thermal runaway"
  cause: "Bootstrap capacitor Cboot (10 µF, X7R) loses >30% capacitance at -40°C due to DC bias derating"
  severity: 9
  occurrence: 4
  detection: 3

- function: "Provide shoot-through protection with 200 ns dead time"
  failure_mode: "Dead time reduces to <50 ns"
  effect: "Cross-conduction between high-side and low-side MOSFETs, peak current >50A, device destruction"
  cause: "Propagation delay mismatch between high-side and low-side gate-driver channels exceeds 150 ns due to temperature drift"
  severity: 10
  occurrence: 5
  detection: 2
```

**Inline comments for the YAML structure:**
- `failure_mode`: Must be a measurable deviation from the function. “Gate voltage falls below 10.8V” is specific; “gate drive fails” is not.
- `effect`: Trace to the next level. Here, the effect is on the MOSFET, not the motor. If the motor stops, that’s a system-level effect—capture it in a separate row or a higher-level FMEA.
- `cause`: Must be a root cause you can act on. “Bootstrap capacitor loses capacitance” is a physical mechanism. “Bad design” is not a cause.

For spreadsheet users, I use this column mapping:

| Column | Example | Rule |
|--------|---------|------|
| Function | Drive MOSFET gate with 12V ±10% at 100 kHz | One function per row |
| Failure Mode | Gate voltage < 10.8V during switching | Observable, measurable |
| Effect | MOSFET linear region → thermal runaway | Consequence, not a new failure |
| Cause | Cboot capacitance loss at -40°C | Root mechanism, not a guess |

## Common Pitfalls & Gotchas

1. **Confusing effect with failure mode.**  
   I’ve seen “motor stops” listed as a failure mode for a gate driver. That’s an effect. The failure mode is “gate drive output stuck low.” If you can’t measure it at the item’s boundary, it’s not a failure mode.

2. **Writing compound causes.**  
   “Capacitor ages and PCB trace corrodes” is two causes. Each failure mode should have one primary cause per row. If multiple causes exist, create separate rows—they may have different occurrence and detection ratings.

3. **Skipping the function.**  
   Without a clear function statement, you can’t define a failure mode. “Drive gate with 12V” is a function. “Work properly” is not. Always write the function first, then ask: *How can this function fail?*

## Try It Yourself

1. **Pick a component from your current project** (e.g., a voltage regulator, an op-amp, a connector). Write its primary function in one sentence. Then list three failure modes that directly violate that function. For each, trace one effect upward and one cause downward.

2. **Take an existing FMEA from your team** and audit the failure chain. For each row, underline the failure mode, circle the effect, and bracket the cause. Count how many rows have a cause that is actually an effect (e.g., “overheating” as a cause of “shutdown”). Refactor at least three rows.

3. **Export your FMEA to YAML or JSON** and run a simple script to check for duplicate failure modes across rows. In a real project, I found 12% of rows were duplicates because the team wrote the same failure mode with slightly different wording. Deduplication forces you to consolidate causes and effects.

## Next Up

Tomorrow: **Severity Rating: AIAG-VDA Scales & Customer Impact**. We’ll break down the 1–10 severity scale from the new AIAG-VDA handbook, with real examples of what a severity 9 vs. 10 looks like in an automotive motor controller. No more guessing—you’ll know exactly how to rate the customer impact of each effect in your failure chain.
