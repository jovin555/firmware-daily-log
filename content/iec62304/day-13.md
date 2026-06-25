---
title: "Day 13: MISRA C for Medical: Compliant Coding Guidelines"
date: 2026-06-25
tags: ["til", "iec62304", "misra", "coding-standards"]
---

## What I Explored Today

Today I dug into how MISRA C maps onto IEC 62304's design and implementation requirements for medical device software. Specifically, I looked at how to configure a static analysis tool (Cppcheck with MISRA add-on) to enforce the subset of MISRA rules that directly support IEC 62304 §5.2.6 (Software Unit Implementation) and §5.3.3 (Integration Testing). The key insight: MISRA C:2012 is not a checkbox—it's a risk-control measure that, when applied correctly, provides objective evidence for the "no undefined behavior" claim required by the standard.

## The Core Concept

IEC 62304 requires that software units be implemented without "undesirable" behavior. The problem is that C is full of undefined and unspecified behaviors—signed integer overflow, sequence point violations, unsequenced modifications, and strict aliasing violations. MISRA C exists to eliminate these from your codebase.

But here's the nuance: MISRA C:2012 has 143 required rules and 16 advisory rules. Not all of them are equally relevant to medical device safety. The real engineering work is in creating a *deviation procedure*—a documented, risk-based decision to not follow a rule, with a justification tied to your hazard analysis. For example, Rule 21.1 (no use of `<stdio.h>`) is trivially deviated if your device has no file system, but you must document why.

The compliance matrix I built today maps each MISRA rule to the IEC 62304 software unit characteristics it supports: determinism, bounded resource usage, and freedom from undefined behavior. This is what auditors actually want to see.

## Key Commands / Configuration / Code

**1. Cppcheck MISRA configuration for IEC 62304 compliance**

```bash
# Install Cppcheck with MISRA add-on (v2.12+)
sudo apt install cppcheck cppcheck-misra

# Run with medical-device-appropriate ruleset
cppcheck --addon=misra \
         --suppress=misra-c2012-21.1 \
         --suppress=misra-c2012-17.7 \
         --suppress=misra-c2012-20.1 \
         --suppress=misra-c2012-20.2 \
         --enable=all \
         --inconclusive \
         --std=c99 \
         --language=c \
         src/
```

**2. Example: MISRA-compliant medical device state machine**

```c
/* MISRA C:2012 compliant state machine fragment */
/* Rule 15.2: single break per switch clause */
/* Rule 16.3: default clause present */
/* Rule 10.1: boolean expression in control */

typedef enum {
    DEVICE_STATE_INIT = 0,
    DEVICE_STATE_IDLE,
    DEVICE_STATE_ACTIVE,
    DEVICE_STATE_ERROR,
    DEVICE_STATE_COUNT  /* not a state, used for bounds checking */
} device_state_t;

static device_state_t current_state = DEVICE_STATE_INIT;

/* Rule 8.13: pointer parameter should be const if not modified */
/* Rule 15.5: function has single exit point */
int32_t process_event(const device_event_t * const event)
{
    int32_t retval = 0;
    bool valid_transition = false;

    if ((event == NULL) || (event->id >= EVENT_COUNT))
    {
        retval = -1;  /* Rule 14.4: non-zero is true */
    }
    else
    {
        switch (current_state)
        {
            case DEVICE_STATE_INIT:
                if (event->id == EVENT_POWER_UP_COMPLETE)
                {
                    current_state = DEVICE_STATE_IDLE;
                    valid_transition = true;
                }
                break;

            case DEVICE_STATE_IDLE:
                if (event->id == EVENT_START_REQUEST)
                {
                    current_state = DEVICE_STATE_ACTIVE;
                    valid_transition = true;
                }
                break;

            case DEVICE_STATE_ACTIVE:
                if (event->id == EVENT_STOP_REQUEST)
                {
                    current_state = DEVICE_STATE_IDLE;
                    valid_transition = true;
                }
                else if (event->id == EVENT_FAULT_DETECTED)
                {
                    current_state = DEVICE_STATE_ERROR;
                    valid_transition = true;
                }
                break;

            case DEVICE_STATE_ERROR:
                if (event->id == EVENT_RESET)
                {
                    current_state = DEVICE_STATE_INIT;
                    valid_transition = true;
                }
                break;

            default:
                /* Rule 16.3: default catches invalid states */
                current_state = DEVICE_STATE_ERROR;
                retval = -2;
                break;
        }

        if (valid_transition == false)
        {
            retval = -3;  /* invalid transition for current state */
        }
    }

    return retval;
}
```

**3. MISRA deviation template for IEC 62304**

```xml
<!-- deviation.xml – part of your Software Safety Classification -->
<deviation>
  <rule-id>MISRA C:2012 Rule 21.1</rule-id>
  <description>Use of stdio.h is prohibited</description>
  <justification>
    This device has no file system, no console, and no external storage.
    All diagnostic output uses hardware UART directly (not stdio).
    Hazard analysis ID: HAZ-042 documents that no safety function depends on stdio.
  </justification>
  <risk-assessment>
    Residual risk: Acceptable. No safety-critical data path uses stdio.
    Mitigation: UART driver is unit-tested per IEC 62304 §5.5.3.
  </risk-assessment>
  <approver>Lead Software Engineer</approver>
  <date>2026-06-25</date>
</deviation>
```

## Common Pitfalls & Gotchas

**1. Treating MISRA as a pass/fail checklist**
The biggest mistake I see is teams running a static analyzer, fixing every violation without understanding *why* the rule exists, then claiming "MISRA compliant." Auditors will ask for your deviation procedure. If you have zero deviations, they'll suspect you disabled rules. A realistic medical project will have 10-20 documented deviations for rules like 21.1 (stdio), 17.7 (function pointer use in bootloader), or 20.1/20.2 (standard library redefinitions).

**2. Forgetting about Rule 1.1 (implementation-defined behavior)**
MISRA C:2012 Rule 1.1 requires that all implementation-defined behaviors be documented. This is where most teams fail. For example, what does `>>` do on signed integers on your compiler? Right-shift of signed negative values is implementation-defined. You must document that your compiler (e.g., GCC for ARM) performs arithmetic right shift, and that this is acceptable per your hazard analysis. Without this documentation, your MISRA compliance is incomplete.

**3. Ignoring advisory rules**
Advisory rules (marked with "Advisory" in the standard) are not optional in a medical context. IEC 62304 §5.2.6 says "software unit implementation shall be verifiable." Advisory rules like Rule 12.1 (parentheses in expressions) directly support verifiability. If you skip advisory rules, you need a deviation for each one—not a blanket "we don't follow advisory rules."

## Try It Yourself

1. **Create your MISRA deviation template**: Take the XML example above and expand it to include fields for: rule category (Required/Advisory), affected software units, and verification method (static analysis, code review, or test). This is what you'll present during an IEC 62304 audit.

2. **Run Cppcheck on your existing codebase**: Use the command from this post. Count how many violations you get in each category (Required vs Advisory). Then, for the top 5 Required violations, write a one-paragraph justification explaining why each one is or isn't relevant to your device's safety.

3. **Audit your switch statements**: Find every `switch` in your codebase. Verify that each one has a `default` clause (MISRA 16.3), that no case falls through without an explicit comment (MISRA 15.2), and that the controlling expression is an integer type (MISRA 16.1). Document any violations as potential deviations.

## Next Up

Tomorrow: **Unit Verification: Code Reviews & Static Analysis** — I'll walk through how to structure a code review checklist that satisfies IEC 62304 §5.5.3 (Software Unit Verification) and how to integrate static analysis results into your verification report, including how to handle false positives without losing audit trail.
