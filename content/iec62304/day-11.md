---
title: "Day 11: Software Architectural Design: Decomposition"
date: 2026-06-23
tags: ["til", "iec62304", "architecture", "design"]
---

## What I Explored Today

Today I dug into the practical mechanics of software decomposition under IEC 62304 Clause 5.2.3 — specifically how to break a medical device software system into software units (SUs) that are independently testable, traceable to hazards, and manageable for a safety-critical project. The standard doesn't prescribe a single decomposition method, but it demands that the decomposition be *justified* and *documented*. I focused on applying structured decomposition using a layered architecture with explicit data flow contracts, and I validated the approach against a real-world infusion pump control module.

## The Core Concept

Decomposition is not just about splitting code into files. Under IEC 62304, decomposition is the process of partitioning the software system into **software units** such that each unit has a single, well-defined responsibility, minimal coupling to other units, and a clear interface that can be verified against its requirements. The *why* is critical: each software unit must be traceable to a software requirement (from the SRS), and each unit must be testable in isolation or through a defined integration test. Poor decomposition leads to untestable units, hidden dependencies, and — worst case — a failure to demonstrate that the software mitigates its identified hazards.

The standard expects you to document the decomposition rationale. For example, if you decompose by function (e.g., `DoseCalculator`, `PumpController`, `AlarmManager`), you must show that this decomposition aligns with the system's safety architecture. If you decompose by hardware abstraction (e.g., `MotorDriver`, `SensorReader`), you must show how that supports fault isolation. I used a **layered decomposition** with three tiers: Application Logic, Safety Monitor, and Hardware Abstraction. Each tier maps to a distinct risk control measure.

## Key Commands / Configuration / Code

I'll demonstrate decomposition using a C-based embedded project for an infusion pump. The key is to define software units as separate modules with explicit interfaces. Here's a minimal but correct example.

**File: `inc/dose_calculator.h`** — Interface for the DoseCalculator software unit.
```c
#ifndef DOSE_CALCULATOR_H
#define DOSE_CALCULATOR_H

#include <stdint.h>
#include <stdbool.h>

// Software Unit: DoseCalculator
// Responsibility: Compute infusion rate from prescribed dose and patient weight.
// Traceability: SRS-REQ-042 (Dose calculation accuracy within +/-1%)
// Hazard: Overinfusion due to calculation error (H-003)

typedef struct {
    float dose_mg_per_kg;   // Prescribed dose in mg/kg
    float patient_weight_kg; // Patient weight in kg
    float concentration_mg_per_ml; // Drug concentration
} DoseParams;

// Returns infusion rate in ml/hr, or 0.0f if parameters are invalid.
// Error codes: 0 = success, -1 = invalid dose, -2 = invalid weight
int32_t DoseCalculator_ComputeRate(const DoseParams *params, float *rate_ml_per_hr);

#endif // DOSE_CALCULATOR_H
```

**File: `src/dose_calculator.c`** — Implementation with input validation.
```c
#include "dose_calculator.h"
#include <math.h>

int32_t DoseCalculator_ComputeRate(const DoseParams *params, float *rate_ml_per_hr) {
    // IEC 62304 requires defensive design: validate all inputs
    if (params == NULL || rate_ml_per_hr == NULL) {
        return -3; // Null pointer error
    }
    if (params->dose_mg_per_kg <= 0.0f || params->dose_mg_per_kg > 100.0f) {
        return -1; // Invalid dose range
    }
    if (params->patient_weight_kg <= 0.0f || params->patient_weight_kg > 500.0f) {
        return -2; // Invalid weight range
    }
    if (params->concentration_mg_per_ml <= 0.0f) {
        return -4; // Invalid concentration
    }

    // Rate = (dose * weight) / concentration
    *rate_ml_per_hr = (params->dose_mg_per_kg * params->patient_weight_kg) /
                      params->concentration_mg_per_ml;

    // Clamp to physical limits (safety check)
    if (*rate_ml_per_hr > 1000.0f) {
        *rate_ml_per_hr = 1000.0f; // Max pump rate
        return 1; // Warning: rate clamped
    }

    return 0; // Success
}
```

**File: `src/pump_controller.c`** — Decomposed unit that uses DoseCalculator.
```c
#include "pump_controller.h"
#include "dose_calculator.h"
#include "motor_driver.h"   // Another software unit
#include "alarm_manager.h"  // Another software unit

// Software Unit: PumpController
// Responsibility: Orchestrate infusion delivery, enforce safety limits.
// Traceability: SRS-REQ-044 (Pump stops on occlusion), SRS-REQ-047 (Rate limits)

int32_t PumpController_StartInfusion(const DoseParams *dose) {
    float rate;
    int32_t calc_result = DoseCalculator_ComputeRate(dose, &rate);
    if (calc_result < 0) {
        AlarmManager_Raise(ALARM_DOSE_ERROR);
        return -1;
    }

    // Decomposed safety check: rate must be within pump capability
    if (rate > PUMP_MAX_RATE_ML_PER_HR) {
        AlarmManager_Raise(ALARM_RATE_EXCEEDED);
        return -2;
    }

    MotorDriver_SetRate(rate);
    MotorDriver_Start();
    return 0;
}
```

**Build system snippet (CMakeLists.txt)** — Shows unit isolation for testing.
```cmake
# Each software unit gets its own test target for unit testing
add_executable(test_dose_calculator
    test/test_dose_calculator.c
    src/dose_calculator.c
)
target_include_directories(test_dose_calculator PRIVATE inc test/mocks)
target_link_libraries(test_dose_calculator PRIVATE unity)  # Unity test framework

add_test(NAME test_dose_calculator COMMAND test_dose_calculator)
```

## Common Pitfalls & Gotchas

1. **Decomposing by file location instead of responsibility.** I've seen teams create `src/utils.c` that contains everything from CRC calculation to string formatting. Under IEC 62304, that's a single software unit with multiple responsibilities — impossible to trace to a single requirement. Each `.c` file should map to exactly one software unit with one primary responsibility. Use a traceability matrix to enforce this.

2. **Ignoring data flow between units.** The standard requires that interfaces between software units be documented. If `DoseCalculator` and `PumpController` share a global variable for the current rate, you've created hidden coupling. Always pass data through explicit function parameters or well-defined message queues. In safety-critical systems, avoid shared global state entirely.

3. **Forgetting to decompose for testability.** If a software unit calls `malloc()` or accesses hardware directly, it's hard to unit test. Decompose so that hardware-dependent units (like `MotorDriver`) are separate from logic units (like `DoseCalculator`). Use mock interfaces for testing. In the example above, `PumpController` depends on `MotorDriver` through a header — you can mock `MotorDriver_SetRate` for unit tests.

## Try It Yourself

1. **Decompose a hazard.** Take one hazard from your device's hazard analysis (e.g., "overinfusion due to software error"). Identify which software units must exist to detect and mitigate that hazard. Write the interface header for one of those units, including a comment block that traces it to the hazard ID.

2. **Audit your current project.** Pick three `.c` files from your existing codebase. For each, list all the responsibilities it handles. If any file has more than one responsibility, refactor it into separate software units. Document the decomposition rationale in a comment at the top of each new file.

3. **Write a unit test for a decomposed unit.** Using the `DoseCalculator` example above, write a test case that verifies the function returns `-1` when `dose_mg_per_kg` is zero. Then write a test that verifies the rate is clamped to 1000.0 ml/hr. Run it with your preferred test framework (Unity, Ceedling, or Google Test).

## Next Up

Tomorrow: **Architectural Design for Safety: Fault Isolation** — how to partition software units so that a failure in one cannot propagate to a safety-critical function. We'll cover spatial and temporal isolation techniques, memory protection units (MPUs), and watchdog-based recovery patterns.
