---
title: "Day 14: Unit Verification: Code Reviews & Static Analysis"
date: 2026-06-26
tags: ["til", "iec62304", "unit-verification", "static-analysis"]
---

## What I Explored Today

Today I dug into IEC 62304 Clause 5.6.3 — Unit Verification. The standard requires that every software unit be verified against its detailed design, and it explicitly names two primary methods: code reviews and static analysis. I spent the day setting up a practical workflow that combines both, using a real embedded C project targeting a Cortex-M4 MCU. The goal was to understand not just *what* the standard demands, but *how* to implement it in a way that doesn't slow down development.

## The Core Concept

Unit verification is the safety net between "I wrote this code" and "this code is correct." IEC 62304 doesn't mandate *how* you verify — it only says you must. But the standard's risk classification (Class A, B, C) directly influences the rigor required. For Class C (no injury possible), a simple peer review might suffice. For Class B (possible non-serious injury), you need documented evidence of both review and static analysis. For Class C (death or serious injury), you need all of that plus structural coverage analysis (which we'll cover later).

The why is straightforward: bugs found during unit verification cost 10x less to fix than those found during integration testing, and 100x less than those found post-market. Static analysis catches the "invisible" defects — buffer overflows, uninitialized variables, dead code — that human reviewers miss. Code reviews catch the logical errors, design deviations, and readability issues that tools cannot. Together, they form a complementary pair.

## Key Commands / Configuration / Code

I set up a verification pipeline using **Cppcheck** (static analysis) and a structured review checklist. Here's the concrete setup.

### Static Analysis with Cppcheck

```bash
# Run Cppcheck with MISRA C:2012 compliance checking
# --enable=all: enables all checks (warning, style, performance, portability, information)
# --suppress=*: we'll selectively enable, not blanket suppress
# --std=c99: our target compiler uses C99
# --xml: output in XML for CI integration
# --suppress=missingIncludeSystem: suppress system header noise
cppcheck --enable=all \
         --suppress=missingIncludeSystem \
         --std=c99 \
         --xml \
         --xml-version=2 \
         src/ 2> cppcheck_report.xml

# Generate a human-readable report
cppcheck --enable=all \
         --suppress=missingIncludeSystem \
         --std=c99 \
         src/ 2>&1 | tee cppcheck_output.txt
```

### Code Review Checklist (IEC 62304 Compliant)

I use this checklist for every unit review. It maps directly to the standard's requirements:

```markdown
## Unit Review Checklist — IEC 62304 §5.6.3

### 1. Correctness Against Detailed Design
- [ ] Unit implements all specified functions (trace to design ID)
- [ ] No extra functionality beyond design (scope creep)
- [ ] Error handling matches design (return codes, error states)

### 2. Code Quality & Maintainability
- [ ] No magic numbers (use named constants)
- [ ] Cyclomatic complexity ≤ 10 (measured with `pmccabe`)
- [ ] Comment-to-code ratio ≥ 20% (measured with `cloc`)
- [ ] No functions > 60 lines (single screen rule)

### 3. Safety-Critical Checks (Class B/C)
- [ ] All pointer dereferences are null-checked
- [ ] No buffer overflows possible (static analysis confirms)
- [ ] No uninitialized variables (static analysis confirms)
- [ ] No dead code (static analysis confirms)
- [ ] No recursion (forbidden in safety-critical units)
```

### Example: A Unit That Fails Static Analysis

```c
// file: src/adc_driver.c
#include "adc_driver.h"

static uint16_t adc_buffer[64];
static uint8_t buffer_index;

void adc_store_sample(void) {
    // BUG: buffer_index may overflow (no bounds check)
    adc_buffer[buffer_index] = adc_read();  // Cppcheck: array index out of bounds
    buffer_index++;
}

int16_t adc_get_sample(uint8_t index) {
    // BUG: no null check on return pointer (design says returns -1 on error)
    return adc_buffer[index];  // Cppcheck: uninitialized variable if index > 63
}
```

Cppcheck output:
```
[src/adc_driver.c:7]: (error) Array 'adc_buffer[64]' accessed at index 64, which is out of bounds.
[src/adc_driver.c:12]: (error) Uninitialized variable: adc_buffer[index] (index may be > 63)
```

The fix is trivial but the tool catches it before it becomes a field failure.

## Common Pitfalls & Gotchas

### 1. False Positives Are Real — But Don't Ignore Them
Every static analysis tool generates false positives. The temptation is to suppress them all with `--suppress=*`. **Don't.** Instead, document each suppression with a rationale in the code:

```c
// cppcheck-suppress nullPointerRedundantCheck
// Rationale: Pointer is validated in calling function per design §4.2.1
```

IEC 62304 auditors will ask for this documentation. A blanket suppression file is a red flag.

### 2. Code Reviews Without a Checklist Are Wasteful
I've seen teams do "code reviews" that are just "looks good to me" rubber stamps. The standard expects documented evidence. Use a checklist that ties each review item to a specific design requirement. If you can't trace a review comment back to a design element, you're not verifying — you're just reading.

### 3. Static Analysis Is Not a Substitute for Design Review
A tool can tell you that `buffer_index` overflows, but it cannot tell you that the design itself is wrong. I once reviewed a unit where the static analysis passed perfectly — but the unit implemented the wrong algorithm entirely. The design called for a median filter, the code implemented a moving average. The tool was happy; the patient would not have been.

## Try It Yourself

1. **Run Cppcheck on your own embedded C project** with `--enable=all --std=c99`. Count how many real defects it finds vs. false positives. Document each false positive with a rationale comment.

2. **Create a code review checklist** for your team that maps to IEC 62304 §5.6.3. Include at least 5 items that are specific to your domain (e.g., "All ISR functions are reentrant" for RTOS projects).

3. **Measure cyclomatic complexity** on your most complex module using `pmccabe`:
   ```bash
   pmccabe *.c | sort -n -r | head -10
   ```
   Refactor any function with complexity > 10 into smaller units. Re-run the analysis.

## Next Up

Tomorrow, I'm tackling **Software Integration & Integration Testing** — the step where we take those verified units and wire them together. I'll cover how to build an integration test harness, handle inter-module dependencies, and what IEC 62304 says about integration test coverage for Class B and C devices. Spoiler: it's not just "does it compile?"
