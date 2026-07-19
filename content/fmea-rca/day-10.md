---
title: "Day 10: D5-D6: Permanent Corrective Actions & Validation"
date: 2026-07-19
tags: ["til", "fmea-rca", "d5", "d6", "corrective-action"]
---

## What I Explored Today

Today I worked through D5 (Choose and Verify Permanent Corrective Actions) and D6 (Implement and Validate Permanent Corrective Actions) of the 8D process. These are the payoff steps — where we stop patching symptoms and actually fix the root cause. I focused on how to select the right corrective action using decision matrices, how to verify it works in a controlled environment, and how to validate it under production conditions. The key insight: D5 is about *proving* the fix works, D6 is about *proving* it works at scale.

## The Core Concept

Most engineers jump straight to implementation when they find a root cause. That’s a trap. D5 forces you to ask: *Is this the best fix, or just the first fix?* You need to evaluate multiple candidate actions against criteria like effectiveness, cost, implementation time, and side effects. A decision matrix (Pugh matrix) is your friend here.

Once you pick the best action, you must **verify** it — typically in a lab or simulation — before you commit to production. Verification answers: *Does the fix actually eliminate the root cause under controlled conditions?*

D6 then takes that verified fix and **validates** it in the real production environment. Validation answers: *Does the fix work when real operators, real materials, and real process variation are present?* This is where you run pilot runs, collect data, and compare against your baseline.

The critical distinction: verification is *did we build the thing right?* Validation is *did we build the right thing?*

## Key Commands / Configuration / Code

### Decision Matrix for Corrective Action Selection (Python snippet)

```python
import pandas as pd
import numpy as np

# Define candidate actions and criteria
candidates = [
    "Add hardware watchdog timer",
    "Increase debounce delay in firmware",
    "Replace mechanical switch with hall-effect sensor",
    "Add redundant sensor with voting logic"
]

criteria = ["Effectiveness", "Cost", "Implementation Time", "Reliability Impact"]
weights = [0.4, 0.2, 0.2, 0.2]  # Must sum to 1.0

# Scores: 1 (worst) to 5 (best)
scores = np.array([
    [5, 3, 4, 5],  # Watchdog
    [3, 5, 5, 3],  # Debounce
    [4, 2, 3, 4],  # Hall-effect
    [5, 1, 2, 5]   # Redundant sensor
])

df = pd.DataFrame(scores, index=candidates, columns=criteria)
df['Weighted Score'] = df.dot(weights)
print(df.sort_values('Weighted Score', ascending=False))
```

### Verification Test Script (Embedded C pseudocode)

```c
// Verification: Test the watchdog timer under fault injection
void verify_watchdog_action(void) {
    uint32_t baseline_resets = read_reset_counter();
    
    // Inject fault: hold CPU in infinite loop
    __disable_irq();
    while(1) {
        // Watchdog should fire within 1000ms
        asm("nop");
    }
    
    // After watchdog reset, check counter
    uint32_t after_resets = read_reset_counter();
    assert(after_resets == baseline_resets + 1);
    
    // Verify system recovers to safe state
    assert(read_system_state() == SAFE_STATE);
    printf("Watchdog verification PASSED\n");
}
```

### Validation Data Collection (Bash + Python)

```bash
# Run 1000 production cycles with the fix deployed
for i in {1..1000}; do
    ./production_test_cycle --log /tmp/validation_run.csv
done

# Compare failure rate against baseline
python3 -c "
import pandas as pd
baseline = pd.read_csv('baseline_failures.csv')
validation = pd.read_csv('/tmp/validation_run.csv')
baseline_rate = baseline['failure'].mean()
validation_rate = validation['failure'].mean()
print(f'Baseline failure rate: {baseline_rate*100:.2f}%')
print(f'Validation failure rate: {validation_rate*100:.2f}%')
print(f'Reduction: {(1 - validation_rate/baseline_rate)*100:.1f}%')
"
```

## Common Pitfalls & Gotchas

1. **Confusing verification with validation** — I’ve seen teams run a single lab test, declare victory, and deploy to production. The lab doesn’t have vibration, temperature swings, or operator variability. Always run a production pilot (at least 100 cycles or 24 hours, whichever is longer) before signing off D6.

2. **Not defining acceptance criteria upfront** — If you don’t know what “good enough” looks like, you’ll never know when to stop. Before you start D5, write down: *What metric must improve? By how much? Over how many samples?* For example: “Failure rate must drop from 2.3% to <0.1% over 1000 consecutive production units.”

3. **Selecting the cheapest fix instead of the most effective** — The decision matrix helps here, but people still bias toward low-cost actions. Remember: the cost of a bad fix is re-opening the 8D, re-implementing, and re-validating. That’s almost always more expensive than doing it right the first time.

## Try It Yourself

1. **Build a decision matrix** for a recent problem you solved. List 3-4 candidate corrective actions, score them against 3 criteria (effectiveness, cost, time), and calculate weighted scores. Were you surprised by the result?

2. **Write a verification test** for a firmware fix you’ve deployed. Use fault injection (e.g., corrupt a sensor reading, disable an interrupt) and assert that the system recovers to a safe state. Run it 100 times in a loop.

3. **Run a validation pilot** on a current project. Deploy your fix to one production line or one shift. Collect failure data for at least 50 cycles and compare it to your baseline. If the improvement isn’t statistically significant, go back to D5.

## Next Up

Tomorrow is D7: Preventing Recurrence — Updating FMEA & Control Plans. We’ll take our validated corrective action and bake it into the design process so the problem never happens again. That means updating the FMEA, writing new control plan entries, and adding automated checks to prevent regression. See you then.
