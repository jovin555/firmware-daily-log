---
title: "Day 12: Defensive Programming for Safety: MISRA & Coding Rules"
date: 2026-06-24
tags: ["til", "cfse", "misra", "defensive", "coding"]
---

## What I Explored Today

Today I dug into the practical application of defensive programming through MISRA-C coding rules for safety-critical firmware. I’ve known about MISRA for years, but today I actually sat down with the MISRA-C:2012 guidelines and a static analysis tool (PC-lint) to see how these rules catch real bugs before they become field failures. The focus was on rules that prevent undefined behavior, enforce strong typing, and eliminate common pitfalls in embedded C.

## The Core Concept

Defensive programming isn’t about writing code that “looks safe.” It’s about writing code that *cannot* fail in unexpected ways, even when inputs are garbage, hardware glitches, or a junior engineer modifies your function. MISRA (Motor Industry Software Reliability Association) provides a set of coding rules that enforce this discipline. The key insight: **the compiler will let you do dangerous things. MISRA rules are guardrails that prevent you from doing them.**

Why does this matter for functional safety? Consider a simple integer overflow. In ISO 26262 ASIL-B and above, you must prove that integer operations cannot cause unintended behavior. MISRA Rule 10.3 (essential type model) forces you to explicitly cast between integer types, making every narrowing conversion visible. This isn’t pedantry—it’s traceable evidence for the safety case.

The real power comes from combining MISRA with static analysis. A human reviewer might miss a subtle implicit cast. A tool like PC-lint or Coverity will flag it every time, and you must either fix it or document a deviation with a formal justification.

## Key Commands / Configuration / Code

Here’s how I set up a minimal MISRA-C:2012 check using PC-lint on a safety-critical module. The goal: enforce rule 10.1 (operands shall not be of inappropriate essential type) and rule 18.4 (pointer arithmetic shall not be used with pointers to incomplete types).

**Example: Dangerous implicit cast (MISRA violation)**

```c
/* File: adc_driver.c */
#include <stdint.h>

uint16_t adc_read(void) {
    uint16_t raw = 0x1FF;  /* 10-bit ADC value */
    uint32_t scaled;
    
    /* Violation: implicit cast from uint16_t to uint32_t is allowed by C,
       but MISRA Rule 10.3 requires explicit cast for essential type change */
    scaled = raw * 100;  /* Potential overflow before promotion */
    
    return (uint16_t)(scaled / 100);
}
```

**Fixed version (MISRA compliant)**

```c
/* File: adc_driver.c */
#include <stdint.h>

uint16_t adc_read(void) {
    uint16_t raw = 0x1FF;
    uint32_t scaled;
    
    /* Explicit cast to uint32_t before multiplication */
    scaled = (uint32_t)raw * 100U;
    
    /* Explicit cast back, with range check */
    if (scaled / 100U > UINT16_MAX) {
        /* Safety: clamp to max */
        return UINT16_MAX;
    }
    return (uint16_t)(scaled / 100U);
}
```

**PC-lint configuration snippet for MISRA-C:2012**

```makefile
# lint-options.mak
LINT_OPTS = \
    -w2 \                    # Warning level 2 (all warnings)
    -e900 \                  # Enable MISRA checking
    -misra(10.1,10.3,18.4) \ # Specific rules to enforce
    +fbo \                   # Function body only (skip headers)
    -i$(INCLUDE_DIRS)        # Include paths
```

Run it:
```bash
lint-nt $(LINT_OPTS) src/adc_driver.c
```

Expected output for the violation:
```
adc_driver.c(8): error 900: MISRA Rule 10.3: implicit conversion from 'uint16_t' to 'uint32_t' in assignment
```

**Another critical rule: Rule 15.4 (no more than one break or goto per loop)**

```c
/* Violation: multiple breaks in a single loop */
for (uint8_t i = 0; i < 10; i++) {
    if (sensor[i] > THRESHOLD_HIGH) {
        error_code = ERROR_OVER;
        break;  /* First break */
    }
    if (sensor[i] < THRESHOLD_LOW) {
        error_code = ERROR_UNDER;
        break;  /* Second break — violation */
    }
}
```

**Compliant version using a flag**

```c
bool found_error = false;
for (uint8_t i = 0; i < 10 && !found_error; i++) {
    if (sensor[i] > THRESHOLD_HIGH) {
        error_code = ERROR_OVER;
        found_error = true;
    } else if (sensor[i] < THRESHOLD_LOW) {
        error_code = ERROR_UNDER;
        found_error = true;
    }
}
```

## Common Pitfalls & Gotchas

1. **Treating MISRA as a checklist instead of a design tool.** I’ve seen teams run a static analyzer once, fix the 200 violations, and declare “MISRA compliant.” Six months later, a new feature introduces a Rule 8.2 violation (function parameter types not explicitly declared) that causes a stack corruption. MISRA must be enforced continuously in CI, not as a one-time audit.

2. **Over-reliance on deviation records.** MISRA allows formal deviations when a rule cannot be followed for a valid reason (e.g., hardware register access requires volatile casts). But I’ve seen deviation records used as a “get out of jail free” card for lazy coding. Every deviation must have a documented safety rationale and be reviewed by a second engineer.

3. **Ignoring the essential type model.** MISRA-C:2012 introduces “essential types” (boolean, character, enum, signed/unsigned integer, floating). The rule 10.1 forbids mixing operands of different essential type categories. A common mistake: using an enum as an array index without an explicit cast. The compiler won’t warn, but MISRA will flag it, and for good reason—enum values can change size across compilers.

## Try It Yourself

1. **Enable MISRA checking in your toolchain.** If you use GCC, add `-Wconversion -Wsign-conversion -Wfloat-equal` to your CFLAGS. These catch a subset of MISRA rules. Run them on your most recent firmware module and count the warnings.

2. **Refactor a function with multiple return paths.** Take any function that has more than one `return` statement (a MISRA Rule 15.5 violation). Rewrite it to have a single exit point using a `status` variable. Measure the change in cyclomatic complexity.

3. **Write a static analysis suppression for a valid deviation.** Suppose you must use `volatile` to read a hardware status register. Write a MISRA deviation record that includes: rule number, file/line, reason (e.g., “hardware register access per datasheet section 12.3”), and reviewer signature.

## Next Up

Tomorrow: **Safe State & Fail-Safe Design Patterns for Firmware** — how to design your system so that when something goes wrong, it fails to a known safe configuration, not into an undefined crash loop. We’ll cover watchdog strategies, safe state machines, and the art of the graceful shutdown.
