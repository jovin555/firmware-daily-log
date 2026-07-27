---
title: "Day 16: Common RCA Anti-Patterns: Stopping at the First Plausible Cause"
date: 2026-07-27
tags: ["til", "fmea-rca", "anti-patterns"]
---

## What I Explored Today

Today I dug into one of the most pervasive anti-patterns in embedded systems root cause analysis: the "first plausible cause" trap. This is where the investigation stops as soon as a single cause that *could* explain the symptom is found, without verifying it or checking for alternative causes. I've seen this kill production lines, ship firmware with latent bugs, and waste weeks of engineering time chasing ghosts. The fix isn't more tools—it's disciplined methodology.

## The Core Concept

The "first plausible cause" anti-pattern is seductive because it feels productive. You see a crash, notice a null pointer dereference in the log, and declare "fixed." But the real root cause might be a race condition that *caused* the pointer to be null, or a memory corruption that overwrote the pointer value. Stopping at the first plausible cause is like diagnosing a fever as "the flu" without checking for infection, inflammation, or drug reaction.

Why does this happen? Three reasons:
1. **Confirmation bias** — we favor evidence that supports our initial hypothesis.
2. **Time pressure** — management wants a fix *now*, not a thorough investigation.
3. **Tooling blind spots** — the first symptom we see is often the easiest to instrument.

The antidote is the **5 Whys with verification** — not just asking "why" five times, but proving each link in the chain with data. In embedded systems, this means:
- Reproducing the failure under controlled conditions
- Instrumenting every hypothesized causal link
- Ruling out alternative causes with specific tests

## Key Commands / Configuration / Code

Here's a practical approach using GDB and a custom assertion framework to force yourself to verify before declaring root cause.

### 1. Use conditional breakpoints to test alternative hypotheses

```gdb
# Instead of stopping at the crash site, set breakpoints at every potential cause
# Example: investigating a UART TX buffer overflow on STM32

# Hypothesis 1: ISR is not clearing the TXE flag
break HAL_UART_TxCpltCallback if uart_handle->Instance->SR & USART_SR_TXE

# Hypothesis 2: DMA is misconfigured (only break if buffer index wraps unexpectedly)
break HAL_UART_Transmit_DMA if uart_handle->TxXferCount > 256

# Hypothesis 3: Interrupt priority is too low, causing missed interrupts
break NVIC_SetPriority if irq_number == USART1_IRQn && priority > 5

# Run and see which breakpoint fires first — that's your first plausible cause
# But don't stop there! Continue and see if others fire too.
```

### 2. Add "cause verification" assertions to your test harness

```c
// rca_verify.h — embed verification points that force you to check alternatives
#ifndef RCA_VERIFY_H
#define RCA_VERIFY_H

#include <assert.h>
#include <stdint.h>

// Macro: assert that a specific cause is the ONLY active cause
// Usage: RCA_VERIFY_SINGLE_CAUSE(cause_id, condition, alternative_mask)
#define RCA_VERIFY_SINGLE_CAUSE(cause_id, condition, alt_mask) do { \
    static uint32_t _rca_cause_hit = 0; \
    if (!(condition)) { \
        _rca_cause_hit |= (1 << (cause_id)); \
    } \
    /* If multiple causes are active, we haven't found root cause */ \
    if (__builtin_popcount(_rca_cause_hit) > 1) { \
        RCA_LOG_ERROR("Multiple causes active: 0x%08X", _rca_cause_hit); \
        /* Force a controlled reset to prevent false fix */ \
        NVIC_SystemReset(); \
    } \
} while(0)

#endif // RCA_VERIFY_H
```

### 3. Use a systematic cause-elimination matrix in your debug log

```python
# rca_matrix.py — run this post-mortem on your crash logs
# Assumes you've tagged log entries with [CAUSE:<id>]

import re
import sys

CAUSE_TAGS = {
    "CAUSE:1": "Null pointer dereference",
    "CAUSE:2": "Stack overflow",
    "CAUSE:3": "Race condition in scheduler",
    "CAUSE:4": "Watchdog timeout due to infinite loop",
    "CAUSE:5": "Memory corruption (heap overflow)"
}

def analyze_crash_log(logfile):
    causes_found = set()
    with open(logfile, 'r') as f:
        for line in f:
            for tag, desc in CAUSE_TAGS.items():
                if tag in line:
                    causes_found.add(desc)
    
    if len(causes_found) == 1:
        print(f"WARNING: Only one cause found: {list(causes_found)[0]}")
        print("This is the FIRST plausible cause — verify alternatives!")
    elif len(causes_found) > 1:
        print(f"Multiple causes detected: {causes_found}")
        print("Good — you're not stopping at the first cause.")
    else:
        print("No cause tags found. Instrument your code first.")
    
    return causes_found

if __name__ == "__main__":
    analyze_crash_log(sys.argv[1])
```

## Common Pitfalls & Gotchas

1. **"It works on my bench" syndrome** — You fix the first plausible cause, the crash stops on your development board, so you declare victory. But the crash only stopped because you changed timing (e.g., added a debug print) or because the root cause is intermittent. Always reproduce the fix on the *original* hardware without debugger attached.

2. **Confusing correlation with causation** — A log shows a corrupted stack frame *and* a failed CRC check. You fix the CRC logic, but the stack corruption was the real cause (the CRC was correct, but the pointer to the CRC result was corrupted). Use the verification assertions above to check both paths independently.

3. **The "obvious" fix that introduces a new bug** — I once saw a team "fix" a UART overrun by increasing the buffer size. The real cause was a priority inversion in the RTOS that delayed the ISR. The buffer increase just masked the symptom until a different interrupt storm hit. Always ask: "If this fix is correct, what else should break?"

## Try It Yourself

1. **The "5 Whys with Evidence" exercise**: Take your last embedded system crash. Write down the first plausible cause you thought of. Now, for each "why," write down *what specific measurement or log entry* would prove that link. If you can't instrument it, you haven't found the root cause.

2. **Instrument a known failure**: Pick a module that has a history of intermittent failures (e.g., a CAN bus driver). Add the `RCA_VERIFY_SINGLE_CAUSE` macro to every error handler. Run the system until it fails, then check how many causes were active. If it's more than one, you've been stopping too early.

3. **Build a cause-elimination matrix**: For your current project, list the top 5 failure modes. For each, write down 3 alternative causes that could produce the same symptom. Then, for each alternative, write a specific test that would *rule it out* (not just "look at the log").

## Next Up

Tomorrow, we'll bridge the gap from analysis to action: **Integrating RCA into CAPA (Corrective & Preventive Action) Systems**. We'll cover how to turn your verified root cause into a corrective action that doesn't just fix the bug, but prevents the entire class of failure from recurring — including how to write CAPA documents that survive audits and actually improve your codebase.
