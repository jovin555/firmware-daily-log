---
title: "Day 08: Detection Rating: Current Controls & Test Coverage"
date: 2026-07-17
tags: ["til", "fmea", "detection", "rating"]
---

## What I Explored Today

Today I dug into the Detection (D) rating in PFMEA/DFMEA — specifically how to evaluate current controls and test coverage. While Severity and Occurrence get most of the attention, Detection is where the rubber meets the road for embedded systems. A firmware bug with Severity 9 and Occurrence 7 is terrifying, but if your static analysis, unit tests, and hardware-in-the-loop (HIL) tests catch it before release, the effective risk drops dramatically. The challenge is quantifying that coverage honestly.

## The Core Concept

Detection rating answers one question: *Given the current controls in place, how likely is it that we will detect the failure mode before the product reaches the customer?* It is **not** about the probability of the failure occurring — that's Occurrence. Detection is about the probability of catching it.

The AIAG-VDA handbook (1st edition) defines Detection ratings from 1 (almost certain detection) to 10 (absolute uncertainty). For embedded systems, the rating depends on:

- **Detection method maturity**: Is it automated (HIL, CI pipeline) or manual (eyeballing waveforms)?
- **Coverage depth**: Does the test exercise the exact failure path, or just a happy path?
- **Timing**: Is detection at design review, during validation, or only in the field?

A common mistake is to conflate "we test a lot" with "we detect this specific failure." You must map each failure mode to a specific control. If your control is "code review" but the failure is a race condition that only manifests under specific interrupt timing, your Detection rating should be 8–10, not 4.

## Key Commands / Configuration / Code

Here's a practical approach using a Python script to calculate Detection ratings based on control type and coverage metrics. This mirrors what I use in our FMEA tooling.

```python
# detection_rating.py — maps control types to AIAG-VDA Detection ratings
# Assumes AIAG-VDA 1st edition criteria

def get_detection_rating(control_type: str, coverage_pct: float) -> int:
    """
    Returns Detection rating (1-10) based on control type and coverage.
    
    Args:
        control_type: 'automated_hil', 'automated_ci', 'manual_test', 'review', 'none'
        coverage_pct: 0.0 to 1.0 — percentage of failure modes covered
    """
    # Detection rating lookup table (AIAG-VDA aligned)
    rating_map = {
        'automated_hil': {
            1.0: 1,   # 100% coverage with HIL
            0.9: 2,   # 90% coverage
            0.8: 3,   # 80% coverage
            0.5: 5,   # 50% coverage
            0.0: 8,   # no coverage
        },
        'automated_ci': {
            1.0: 2,   # CI with full regression
            0.9: 3,
            0.8: 4,
            0.5: 6,
            0.0: 9,
        },
        'manual_test': {
            1.0: 4,   # exhaustive manual test
            0.9: 5,
            0.8: 6,
            0.5: 7,
            0.0: 10,
        },
        'review': {
            1.0: 6,   # formal inspection
            0.9: 7,
            0.8: 8,
            0.5: 9,
            0.0: 10,
        },
        'none': {0.0: 10},
    }
    
    # Find nearest coverage key
    control_ratings = rating_map.get(control_type, rating_map['none'])
    keys = sorted(control_ratings.keys())
    
    for i, key in enumerate(keys):
        if coverage_pct >= key:
            if i == len(keys) - 1:
                return control_ratings[key]
            # Linear interpolation between keys
            next_key = keys[i+1]
            if coverage_pct < next_key:
                return control_ratings[key]
    return 10

# Example usage for a firmware watchdog failure mode
# Control: automated HIL test that checks watchdog timeout
# Coverage: 95% of watchdog scenarios covered
rating = get_detection_rating('automated_hil', 0.95)
print(f"Detection rating: {rating}")  # Output: Detection rating: 2
```

For test coverage analysis in embedded C projects, I use `gcov` with a custom script to map coverage to failure modes:

```bash
# Generate coverage data for a specific module
gcc -fprofile-arcs -ftest-coverage -o test_fw test_fw.c fw_module.c
./test_fw
gcov fw_module.c

# Parse gcov output to extract line coverage for critical paths
# Example: check if watchdog reset path is covered
awk '/watchdog_reset/ {print $1, $2}' fw_module.c.gcov
# Output: "#####:  42: watchdog_reset();"  -> not covered (#####)
```

## Common Pitfalls & Gotchas

1. **Rating inflation from "testing in general"**  
   Engineers often give Detection a 3 or 4 because "we have unit tests." But if the specific failure mode (e.g., stack overflow under high interrupt load) isn't tested, the rating should be 8+. Always ask: *Is there a test that explicitly exercises this failure path?* If not, bump the rating.

2. **Confusing detection with prevention**  
   A hardware watchdog is a prevention control (Occurrence reduction), not a detection control. Detection controls are things like HIL tests that check if the watchdog fires correctly. Don't double-count the same control in both Occurrence and Detection ratings.

3. **Ignoring coverage granularity**  
   "We have 90% line coverage" sounds good, but if the uncovered 10% includes the exact failure path, your Detection rating is 10 for that failure. Always map coverage to the specific failure mode, not the module average.

## Try It Yourself

1. **Map your CI pipeline to Detection ratings**  
   Take your top 5 failure modes from your last FMEA. For each, list the specific test (unit, integration, HIL) that targets it. If no test exists, assign Detection = 10. If a test exists but doesn't cover the exact failure path, assign Detection = 7–9.

2. **Run gcov on a critical module**  
   Compile your firmware with `-fprofile-arcs -ftest-coverage`, run your test suite, and use `gcov` to check coverage on the exact lines where your failure mode occurs. Update your FMEA Detection rating based on real data.

3. **Build a Detection rating calculator**  
   Use the Python script above as a starting point. Add your own control types (e.g., `formal_verification`, `fuzz_testing`) and calibrate the ratings based on your team's historical detection rates.

## Next Up

Tomorrow we'll tackle the great debate: **RPN vs Action Priority (AP): Old vs New AIAG-VDA Approach**. The classic RPN (Severity × Occurrence × Detection) has been criticized for its mathematical flaws — is a 4×5×6 really the same risk as a 3×4×10? The new AP tables aim to fix that. I'll show you the exact decision matrices and when to use each.
