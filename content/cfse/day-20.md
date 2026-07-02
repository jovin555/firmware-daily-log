---
title: "Day 20: Full Review: Safety Case for a Zephyr-Based Medical Device"
date: 2026-07-02
tags: ["til", "cfse", "review", "project", "safety-case"]
---

## What I Explored Today

Today I completed a full structured review of a safety case for a Zephyr RTOS-based infusion pump controller. This wasn't a code review or a design review—it was an *argument review*. The safety case is the top-level deliverable that ties together every hazard analysis, requirement, verification result, and configuration management artifact into a coherent, defensible claim that the device is acceptably safe. I walked through the GSN (Goal Structuring Notation) diagram, traced every claim down to evidence, and checked for gaps in the argument chain. The device uses Zephyr’s kernel with a custom scheduler configuration, and the safety case had to account for RTOS-specific failure modes like priority inversion and watchdog expiration.

## The Core Concept

A safety case is not a document you write once and file away. It is a living argument that must be *reviewable*. The key insight is that a safety case fails in two ways: (1) the argument is logically incomplete (a gap), or (2) the evidence does not actually support the claim (a mismatch). In embedded systems, especially with an RTOS like Zephyr, the most common gaps involve assumptions about the kernel’s behavior under fault conditions. For example, a claim that “the watchdog will reset the system within 100 ms of a task lockup” must be backed by evidence showing the watchdog ISR priority, the task’s priority, and the actual reset timing measured on target hardware. Without that chain, the claim is just a wish.

The review process I used follows the *defeater-based* approach: for every claim, I asked “what could make this claim false?” and then checked whether the safety case explicitly addresses that defeater. This is more rigorous than a simple checklist review because it forces you to think like an adversary.

## Key Commands / Configuration / Code

I started by extracting the GSN model from the project’s repository. The team uses the open-source `gsn-tool` to maintain the argument structure in YAML. Here’s the top-level goal node:

```yaml
# gsn/goals/infusion_pump_safety.yaml
goals:
  - id: G1
    description: "The infusion pump controller is acceptably safe for its intended use."
    type: top
    context: "IEC 62304 Class C, IEC 60601-1, ISO 14971"
    strategy: S1
    subgoals:
      - G1.1  # All hazardous conditions are controlled
      - G1.2  # Safety functions are correctly implemented
      - G1.3  # Residual risk is acceptable
```

To verify the evidence links, I used `gsn-tool` to export the evidence trace:

```bash
# Export evidence trace to CSV for review
gsn-tool export --project ./infusion_pump --output evidence_trace.csv
```

The CSV showed that subgoal G1.2 (“safety functions correctly implemented”) had evidence from unit tests, but the integration test for the watchdog + task priority scenario was missing. I flagged this as a gap.

Next, I reviewed the Zephyr kernel configuration that the safety case relies on. The relevant Kconfig fragment:

```kconfig
# prj.conf excerpt for safety-critical configuration
CONFIG_SCHED_DEADLINE=n          # Not using deadline scheduling
CONFIG_SCHED_SCALABLE=y          # O(1) scheduler for deterministic behavior
CONFIG_MAIN_STACK_SIZE=4096      # Verified against worst-case stack usage
CONFIG_WATCHDOG_TIMEOUT_MSEC=100 # Must be < 150 ms per SRS-42
CONFIG_ISR_STACK_SIZE=2048       # Verified with stack analysis tool
```

I cross-referenced these values against the safety requirements specification (SRS). The watchdog timeout of 100 ms matched SRS-42, but the stack sizes were only verified with static analysis—no dynamic stack watermarking was enabled. That’s a potential defeater: if the static analysis missed a path, the stack could overflow silently.

Finally, I ran the Zephyr stack analyzer on the actual firmware binary to get runtime data:

```bash
# Build with stack canary and run on target
west build -b stm32f429i_disc1 -t run -- -DCONFIG_STACK_SENTINEL=y
# After running the fault injection tests, extract stack usage
west debug --runner openocd --command "monitor reset halt"
west debug --runner openocd --command "stack_usage" > stack_report.txt
```

The stack report showed that `main` stack peaked at 3,872 bytes—within the 4,096 allocation, but only 224 bytes of margin. That’s tight for a safety-critical system. I recommended increasing to 5,120 bytes with a documented rationale.

## Common Pitfalls & Gotchas

1. **Assuming the RTOS kernel is “safe by default.”** Zephyr’s kernel is not certified to any safety standard out of the box. The safety case must include evidence that the specific kernel configuration (scheduler, ISR priorities, memory protection) has been verified for the target application. I’ve seen teams copy a prj.conf from a demo board and claim it’s safe—that’s a guaranteed audit finding.

2. **Missing the “context” in GSN nodes.** A common mistake is to write a goal like “The system detects over-infusion” without specifying the context (e.g., “within 50 ms of a flow sensor fault”). Without context, the evidence cannot be evaluated. Always include measurable, testable parameters in the context field.

3. **Forgetting to trace evidence back to the hazard.** Every piece of evidence must link to a specific hazard from the HARA (Hazard Analysis and Risk Assessment). I found a test report for “battery voltage monitoring” that was thorough, but it didn’t reference any hazard. The test was irrelevant to safety unless it was tied to a hazard like “battery failure leads to uncontrolled infusion.”

## Try It Yourself

1. **Extract and review the evidence trace** from your own project’s safety case (or a sample GSN model). Use `gsn-tool export` or manually list every leaf node and check if it has a verifiable artifact (test report, analysis, inspection record). Flag any leaf node that only has a “design document” as evidence—that’s usually insufficient.

2. **Perform a defeater analysis** on one safety claim in your system. Write down three things that could make that claim false (e.g., “watchdog fails to reset due to ISR priority inversion”). Then check if your safety case explicitly addresses those defeaters. If not, add a new subgoal or context node.

3. **Run Zephyr’s stack sentinel** on your target board with fault injection. Configure `CONFIG_STACK_SENTINEL=y` and `CONFIG_STACK_SENTINEL_INTERVAL=100`. Then inject a stack overflow (e.g., by calling a recursive function) and verify that the system resets within the watchdog timeout. Document the result as evidence for your safety case.

## Next Up

Tomorrow, I’ll conduct a **Full Review** of the verification artifacts for the infusion pump’s software unit tests—specifically, how to audit test coverage against the safety requirements and spot common gaps in boundary value analysis.
