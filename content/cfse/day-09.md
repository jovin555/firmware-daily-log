---
title: "Day 09: ISO 26262 Part 6: Product Development at SW Level"
date: 2026-06-22
tags: ["til", "cfse", "iso26262", "part6", "software"]
---

## What I Explored Today

Today I dove into ISO 26262 Part 6, which governs product development at the software level for automotive safety-critical systems. This is where the rubber meets the road — Part 6 translates the high-level safety goals from Part 3 (concept phase) and Part 4 (system level) into concrete software engineering practices. I focused on the V-model structure for software development, the required work products (software safety requirements, architecture, unit design, and verification), and the specific techniques for ASIL decomposition at the software level. The key takeaway: Part 6 demands that every software artifact be traceable, verifiable, and free from systematic faults, with specific methods mandated per ASIL level.

## The Core Concept

Why does ISO 26262 dedicate an entire part to software? Because software failures are *systematic* — they don't wear out like hardware, but they can be introduced at any stage of development. Part 6 forces you to prevent, detect, and eliminate these faults through a structured process.

The core concept is the **V-model for software development**, which mirrors the system V-model but at a finer granularity. The left side of the V is specification and design (software safety requirements → software architectural design → software unit design and implementation). The right side is verification and validation (unit testing → integration testing → software safety requirements testing). The bottom of the V is the actual coding.

The critical insight: Part 6 requires **freedom from interference** between software elements with different ASIL levels. If you have an ASIL D element and an ASIL A element running on the same ECU, you must prove they don't corrupt each other — typically through spatial and temporal isolation (e.g., memory partitioning, time-triggered scheduling).

## Key Commands / Configuration / Code

Let's look at a practical example: implementing a software safety requirement for an ASIL C brake-by-wire system. We need a watchdog-based runtime monitoring pattern.

### 1. Software Safety Requirement (SSR) Traceability

```c
/**
 * @brief Software Safety Requirement: SSR_BRAKE_012
 * @id SSR_BRAKE_012
 * @asil ASIL_C
 * @description The brake pressure calculation shall complete within 5ms
 *              of the pedal position sensor reading. If exceeded, the
 *              system shall enter safe state (apply mechanical backup).
 * @source SYS_REQ_BRAKE_004 (System-level safety goal)
 */
```

### 2. Architectural Design — Watchdog Manager Configuration (AUTOSAR-style)

```c
// Watchdog manager configuration for ASIL C supervision
// This is typically in a BSW configuration file (e.g., WdgM_PBcfg.c)

const WdgM_ConfigType WdgMConfig = {
    .WdgM_GlobalConfig = {
        .WdgM_Mode = WdGM_MODE_ON,          // Always active
        .WdgM_DefaultMode = WdGM_MODE_ON,
        .WdgM_AliveSupervision = TRUE,       // Check task is alive
        .WdgM_DeadlineSupervision = TRUE     // Check timing constraints
    },
    .WdgM_SupervisedEntity = {
        .SE_Id = 1,                          // Supervised Entity ID
        .SE_AliveSupervision = {
            .AliveSupervisionType = WDG_ALIVE_CHECKPOINT,
            .ExpectedAliveIndications = 100,  // Expect 100 checkpoints per cycle
            .MinMargin = 5,                   // Allow ±5 tolerance
            .MaxMargin = 5
        },
        .SE_DeadlineSupervision = {
            .DeadlineSupervisionType = WDG_DEADLINE_TIME,
            .ExpectedDeadline = 5000,         // 5ms in microseconds
            .MaxMargin = 500                  // 0.5ms tolerance
        }
    }
};
```

### 3. Unit Implementation with Safety Mechanisms

```c
#include "BrakeControl.h"
#include "WdgM.h"        // Watchdog manager
#include "E2E.h"         // End-to-end communication protection
#include "SafetyMem.h"   // Safety-related memory protection

// ASIL C critical function — must be verified with MC/DC coverage
static uint16_t CalculateBrakePressure(uint16_t pedalPosition)
{
    uint16_t pressure;
    static uint16_t lastPressure = 0;
    
    // E2E protection on input data (CRC + counter)
    E2E_P01Protect(&pedalPosition, sizeof(pedalPosition));
    
    // Range check — ASIL C requires input validation
    if (pedalPosition > PEDAL_MAX_RAW)
    {
        SafetyMem_SetFault(FAULT_PEDAL_OUT_OF_RANGE);
        return SAFE_STATE_PRESSURE;
    }
    
    // Core calculation with overflow protection
    pressure = (pedalPosition * BRAKE_GAIN) >> BRAKE_SHIFT;
    
    // Rate limiter — prevent sudden pressure changes
    if (pressure > (lastPressure + PRESSURE_RAMP_LIMIT))
    {
        pressure = lastPressure + PRESSURE_RAMP_LIMIT;
    }
    
    // E2E protection on output data
    E2E_P01Protect(&pressure, sizeof(pressure));
    
    // Report checkpoint to watchdog
    WdgM_CheckpointReached(SE_BRAKE_CONTROL, CP_PRESSURE_CALC_DONE);
    
    lastPressure = pressure;
    return pressure;
}
```

### 4. Unit Test Example (using CUnit with MISRA-C compliance)

```c
void test_CalculateBrakePressure_Overflow(void)
{
    uint16_t result;
    
    // Test: Input at maximum should not overflow
    result = CalculateBrakePressure(PEDAL_MAX_RAW);
    CU_ASSERT(result <= PRESSURE_MAX_SAFE);
    
    // Test: Input at zero should return zero
    result = CalculateBrakePressure(0);
    CU_ASSERT(result == 0);
    
    // Test: Rate limiter prevents rapid increase
    result = CalculateBrakePressure(PEDAL_MAX_RAW);
    result = CalculateBrakePressure(PEDAL_MAX_RAW);  // Immediate second call
    CU_ASSERT(result <= (PRESSURE_RAMP_LIMIT * 2));
}
```

## Common Pitfalls & Gotchas

1. **Confusing ASIL decomposition with ASIL tailoring** — ASIL decomposition (Part 9, Clause 5) lets you split an ASIL D requirement into ASIL C(D) + ASIL A(D) with sufficient independence. But many engineers forget that decomposition requires *evidence of independence* — you can't just declare it. You need spatial isolation (different memory regions), temporal isolation (different time slots), and communication isolation (no shared variables). Without proof, the decomposition is invalid.

2. **Ignoring tool qualification for static analysis** — Part 6 requires static analysis for ASIL B and above (Table 1 in Clause 6.4.9). But if you use a static analyzer that isn't qualified to TCL (Tool Confidence Level) 3, the analysis results aren't valid evidence. I've seen teams run PC-lint on ASIL D code without qualifying the tool — the auditor rejected it. You need either a qualified tool (e.g., Polyspace qualified for ASIL D) or a tool confidence measure (TCM) argument.

3. **Underestimating MC/DC coverage requirements** — For ASIL C and D, Part 6 requires Modified Condition/Decision Coverage (MC/DC) at the unit level. This is *not* just branch coverage. MC/DC requires that every condition in a decision independently affects the outcome. For a simple `if (a && b)` you need 4 test cases (not 2). Many teams discover this late and have to rewrite tests, blowing the schedule.

## Try It Yourself

1. **Traceability audit**: Take one software safety requirement from your current project. Trace it backward to a system-level safety goal and forward to the implementing function(s) and test case(s). Verify that the traceability matrix has no gaps — every requirement must link to a test, and every test must link to a requirement.

2. **Implement a watchdog checkpoint**: Write a 10ms periodic task (e.g., a sensor fusion function) and add alive supervision checkpoints using the AUTOSAR WdgM API pattern shown above. Test that the watchdog triggers a reset if you artificially delay the task by 15ms.

3. **MC/DC analysis**: Take a decision in your code with at least 3 conditions (e.g., `if (a && b || c)`). Write the minimum set of test cases to achieve 100% MC/DC coverage. Use a coverage tool (like LDRA or Cantata) to verify you hit all conditions.

## Next Up

Tomorrow, I'll tackle **Safety Case: Goal Structuring Notation (GSN)** — how to structure a compelling argument that your system is acceptably safe, using graphical notation that auditors actually understand. We'll build a GSN model for a real airbag deployment system.
