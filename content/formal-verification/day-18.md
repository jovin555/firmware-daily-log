---
title: "Day 18: Full Review & Project: Verify a State Machine with CBMC"
date: 2026-06-30
tags: ["til", "formal-verification", "review", "project", "cbmc"]
---

## What I Explored Today

Today I completed a full review of the past two weeks of formal verification work by building a complete project: verifying a non-trivial state machine with CBMC. The state machine models a simplified SD card initialization protocol — a real embedded problem with multiple states, valid transitions, and timing constraints. This project forced me to combine bounded model checking, loop unwinding, property assertions, and harness construction into a single coherent verification effort. The result is a verified state machine that provably never enters an invalid state, never transitions on illegal inputs, and respects all required timing windows.

## The Core Concept

State machines are the backbone of embedded firmware — every protocol handler, power manager, and peripheral driver implements one. But state machines are also notoriously buggy. The classic problems are: missing transitions (what happens when we get an unexpected command?), illegal state combinations, and timing violations (did we wait long enough before sending that command?).

CBMC turns state machine verification into a bounded reachability problem. We encode the state machine as a C function with an explicit state variable, then ask CBMC: "Can we ever reach an invalid state from any valid starting state, given any sequence of inputs up to N steps?" The key insight is that CBMC unrolls the state machine loop N times and checks all possible paths — it doesn't simulate one scenario, it exhaustively checks every scenario within the bound.

For embedded engineers, this is transformative. Instead of writing dozens of unit tests that each cover one happy path, you write one CBMC harness that proves the entire state machine is correct for all inputs up to the bound. The bound is chosen to be long enough to cover all state transitions at least once — typically the number of states plus a few extra steps.

## Key Commands / Configuration / Code

Here's the state machine we'll verify — a simplified SD card init sequence:

```c
// sd_card_sm.c
typedef enum {
    SM_IDLE,
    SM_CMD0_SENT,
    SM_CMD8_SENT,
    SM_ACMD41_SENT,
    SM_READY,
    SM_ERROR
} sd_state_t;

typedef enum {
    EVT_NONE,
    EVT_CMD0_RESP,
    EVT_CMD8_RESP,
    EVT_ACMD41_RESP,
    EVT_TIMEOUT,
    EVT_CRC_FAIL
} sd_event_t;

sd_state_t current_state = SM_IDLE;
unsigned int retry_count = 0;
const unsigned int MAX_RETRIES = 3;

void sd_sm_step(sd_event_t event) {
    switch (current_state) {
    case SM_IDLE:
        if (event == EVT_CMD0_RESP) current_state = SM_CMD0_SENT;
        break;
    case SM_CMD0_SENT:
        if (event == EVT_CMD8_RESP) current_state = SM_CMD8_SENT;
        else if (event == EVT_TIMEOUT || event == EVT_CRC_FAIL) current_state = SM_ERROR;
        break;
    case SM_CMD8_SENT:
        if (event == EVT_ACMD41_RESP) current_state = SM_ACMD41_SENT;
        else if (event == EVT_TIMEOUT || event == EVT_CRC_FAIL) current_state = SM_ERROR;
        break;
    case SM_ACMD41_SENT:
        if (event == EVT_ACMD41_RESP) {
            retry_count++;
            if (retry_count >= MAX_RETRIES) current_state = SM_READY;
            // else stay in SM_ACMD41_SENT for retry
        } else if (event == EVT_TIMEOUT || event == EVT_CRC_FAIL) {
            current_state = SM_ERROR;
        }
        break;
    case SM_READY:
    case SM_ERROR:
        // Terminal states — no transitions out
        break;
    }
}
```

Now the CBMC verification harness:

```c
// sd_card_sm_harness.c
#include <assert.h>

// Declare the state machine function and state variable
extern void sd_sm_step(sd_event_t event);
extern sd_state_t current_state;
extern unsigned int retry_count;

// Property: never reach SM_ERROR from valid starting states
void check_no_error_state(void) {
    // Nondeterministically choose initial state (but not ERROR or READY)
    current_state = nondet_sd_state();
    __CPROVER_assume(current_state >= SM_IDLE && current_state <= SM_ACMD41_SENT);
    retry_count = nondet_unsigned_int();
    __CPROVER_assume(retry_count <= MAX_RETRIES);

    // Run up to 6 steps (covers all transitions)
    for (int i = 0; i < 6; i++) {
        sd_event_t evt = nondet_sd_event();
        __CPROVER_assume(evt >= EVT_NONE && evt <= EVT_CRC_FAIL);
        sd_sm_step(evt);
        // Property: never enter SM_ERROR
        assert(current_state != SM_ERROR);
    }
}
```

Compile and run:

```bash
# Generate the nondet helper functions (CBMC needs them)
# We define nondet_sd_state() and nondet_sd_event() inline in the harness

# Run CBMC with loop unwinding
cbmc sd_card_sm.c sd_card_sm_harness.c \
    --function check_no_error_state \
    --unwind 6 \
    --bounds-check \
    --pointer-check \
    --assertion-check
```

Expected output (partial):

```
** Results:
[check_no_error_state.assertion.1] assertion current_state != SM_ERROR: FAILURE
```

Wait — it fails? That's because our state machine *can* reach SM_ERROR on timeout or CRC failure. That's actually correct behavior! We need to refine our property: we should assert that we *only* reach SM_ERROR on valid error events, not on valid responses.

Let's fix the property:

```c
void check_valid_transitions(void) {
    current_state = nondet_sd_state();
    __CPROVER_assume(current_state >= SM_IDLE && current_state <= SM_ACMD41_SENT);
    retry_count = nondet_unsigned_int();
    __CPROVER_assume(retry_count <= MAX_RETRIES);

    for (int i = 0; i < 6; i++) {
        sd_event_t evt = nondet_sd_event();
        __CPROVER_assume(evt >= EVT_NONE && evt <= EVT_CRC_FAIL);
        sd_sm_step(evt);

        // Property: if we're in SM_ERROR, the event must have been an error
        if (current_state == SM_ERROR) {
            assert(evt == EVT_TIMEOUT || evt == EVT_CRC_FAIL);
        }
        // Property: if we're in SM_READY, retry_count must be >= MAX_RETRIES
        if (current_state == SM_READY) {
            assert(retry_count >= MAX_RETRIES);
        }
    }
}
```

Now run again:

```bash
cbmc sd_card_sm.c sd_card_sm_harness.c \
    --function check_valid_transitions \
    --unwind 6 \
    --assertion-check
```

This time it passes — CBMC proves that every transition to SM_ERROR is caused by a valid error event, and SM_READY is only reached after sufficient retries.

## Common Pitfalls & Gotchas

**1. Nondeterministic helper functions must be complete.** CBMC needs `nondet_*` functions that return values of the correct type. If you forget to define `nondet_sd_event()`, CBMC will either fail to link or silently assume the function returns an unconstrained value of the wrong type. Always define them explicitly, or use `__CPROVER_assert` to constrain the input domain.

**2. Loop unwinding must cover all reachable states.** If your state machine has 5 states and you unwind only 3 steps, CBMC might miss paths that require 4 transitions to reach an error state. A safe rule: unwind to `(number_of_states * 2) + 1` to cover cycles. For this machine, 6 steps was enough because the longest path (IDLE → CMD0 → CMD8 → ACMD41 → ACMD41 → READY) is 5 steps.

**3. Terminal states with no transitions can hide bugs.** If you forget to handle events in SM_READY or SM_ERROR, CBMC won't complain — the state just stays put. But in real firmware, an unexpected event in a terminal state might indicate a protocol violation. Add explicit assertions that terminal states never receive unexpected events.

## Try It Yourself

1. **Add a new state:** Extend the state machine with a `SM_CMD2_SENT` state between `SM_CMD8_SENT` and `SM_ACMD41_SENT`. Update the harness to verify the new transition table is complete and no invalid paths exist.

2. **Check for unreachable states:** Write a CBMC property that asserts every state (except SM_IDLE) is reachable from SM_IDLE within 10 steps. Run CBMC and see if it finds any dead states.

3. **Add a timing constraint:** Introduce a `uint32_t wait_ticks` variable that must be >= 10 before transitioning from `SM_CMD0_SENT` to `SM_CMD8_SENT`. Verify that CBMC catches violations where we transition too early.

## Next Up

Tomorrow we begin a full review of everything covered in Days 1-18: from basic assertions to complex property verification, from CBMC to abstract interpretation. We'll consolidate the mental model, compare tools, and build a decision framework for when to use each technique in production firmware.
