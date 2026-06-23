---
title: "Day 11: Software Safety Requirements: Deriving from Hazards"
date: 2026-06-23
tags: ["til", "cfse", "safety-requirements", "hazards"]
---

## What I Explored Today

Today I worked through the critical transition from hazard analysis to concrete software safety requirements. In my project—a steer-by-wire system—the HARA identified a hazard: "Unintended steering actuation during high-speed driving" (ASIL D). The gap between that hazard statement and a software requirement that a developer can implement is enormous. I spent the day learning how to decompose that hazard into functional safety requirements (FSRs) and then into technical safety requirements (TSRs) that live in the software requirements specification. The key tool I used was the "safety goal decomposition" pattern from ISO 26262-6, combined with formalizing the requirements using the EARS (Easy Approach to Requirements Syntax) notation.

## The Core Concept

The fundamental problem: a hazard is a system-level condition. Software doesn't "see" hazards—it sees inputs, states, and outputs. The job of the safety engineer is to create a traceable chain from hazard → safety goal → functional safety requirement → technical safety requirement → software safety requirement.

The *why* is traceability and verifiability. If a software engineer writes code that checks "if (steering_angle > MAX_ANGLE) then inhibit_motor()", that code must be traceable back to a specific requirement that was derived from a specific hazard. Without this chain, you cannot prove to an auditor that your software actually mitigates the hazard.

The decomposition follows a pattern:
1. **Safety Goal** (SG): "The system shall prevent unintended steering actuation above 30 km/h." (ASIL D)
2. **Functional Safety Requirement** (FSR): "The steering controller shall detect invalid steering commands and inhibit motor torque within 10 ms."
3. **Technical Safety Requirement** (TSR): "The software shall compare commanded steering angle against a plausibility model of maximum allowable angle based on vehicle speed."
4. **Software Safety Requirement** (SSR): "The SW component `SteeringPlausibilityCheck` shall compute `max_allowed_angle = f(vehicle_speed)` using a lookup table with linear interpolation, and shall assert a fault flag if `commanded_angle > max_allowed_angle + HYSTERESIS`."

Each level adds implementation detail while maintaining the safety intent.

## Key Commands / Configuration / Code

Here's how I structure the requirements in a requirements management tool (e.g., DOORS, Jama, or even a structured YAML file for traceability):

```yaml
# safety_requirements_traceability.yaml
hazards:
  - id: HAZ-001
    description: "Unintended steering actuation during high-speed driving"
    asil: D
    safety_goal:
      id: SG-001
      description: "Prevent unintended steering actuation above 30 km/h"
      asil: D
      functional_safety_requirements:
        - id: FSR-001
          description: "The steering controller shall detect invalid steering commands and inhibit motor torque within 10 ms"
          asil: D
          technical_safety_requirements:
            - id: TSR-001
              description: "The software shall compare commanded steering angle against a plausibility model of maximum allowable angle based on vehicle speed"
              asil: D
              software_safety_requirements:
                - id: SSR-001
                  description: "The SW component SteeringPlausibilityCheck shall compute max_allowed_angle = f(vehicle_speed) using a lookup table with linear interpolation"
                  ears_pattern: "WHEN <vehicle_speed_available> AND <steering_command_received> THEN <compute_max_allowed_angle>"
                  asil: D
                - id: SSR-002
                  description: "The SW component SteeringPlausibilityCheck shall assert a fault flag if commanded_angle > max_allowed_angle + HYSTERESIS"
                  ears_pattern: "WHEN <commanded_angle_exceeds_max_allowed> THEN <assert_fault_flag> WITHIN <1_ms>"
                  asil: D
```

For the actual implementation of the plausibility check, here's a C snippet that implements SSR-001 and SSR-002:

```c
// steering_plausibility.c
#include "steering_plausibility.h"
#include "lookup_table.h"

// Lookup table: vehicle_speed_kmh -> max_allowed_angle_deg
// Defined per TSR-001, derived from vehicle dynamics model
static const lookup_entry_t speed_to_max_angle[] = {
    { .x = 0.0f,  .y = 540.0f },  // parking speeds: full lock
    { .x = 30.0f, .y = 180.0f },  // city speeds: reduced range
    { .x = 80.0f, .y = 45.0f  },  // highway: small corrections only
    { .x = 130.0f,.y = 15.0f  }   // Autobahn: minimal steering
};
#define HYSTERESIS_DEG 2.0f  // per SSR-002, prevents chatter

// Implements SSR-001: compute max allowed angle from speed
float steering_plausibility_get_max_angle(float vehicle_speed_kmh) {
    // Linear interpolation between table entries
    return lookup_table_interpolate(speed_to_max_angle,
                                    ARRAY_SIZE(speed_to_max_angle),
                                    vehicle_speed_kmh);
}

// Implements SSR-002: check command against plausibility
bool steering_plausibility_check(float commanded_angle_deg,
                                 float vehicle_speed_kmh) {
    float max_allowed = steering_plausibility_get_max_angle(vehicle_speed_kmh);
    // Fault if commanded exceeds max + hysteresis
    if (commanded_angle_deg > (max_allowed + HYSTERESIS_DEG)) {
        // Assert fault flag per SSR-002
        safety_fault_raise(FAULT_STEERING_PLAUSIBILITY);
        return false;  // command is invalid
    }
    return true;  // command is plausible
}
```

## Common Pitfalls & Gotchas

1. **Jumping directly from hazard to code.** I've seen teams write "the software shall prevent unintended steering" as a requirement. That's not a requirement—it's a wish. You must decompose until each requirement is testable and implementable by a single software component. If a requirement has "and" in it, split it.

2. **Ignoring timing in the decomposition.** The safety goal might say "prevent unintended actuation," but the software needs to know *how fast* it must react. Without a timing requirement (e.g., "within 10 ms"), the developer might implement a polling loop that runs at 10 Hz, which is useless for ASIL D. Always derive timing from the hazard's worst-case scenario.

3. **Losing the ASIL decomposition.** When you split a safety goal into multiple requirements, the ASIL doesn't automatically split. If you have one ASIL D requirement and one ASIL A requirement that together satisfy the safety goal, the ASIL A requirement must still be developed to ASIL D unless you have proven independence (e.g., separate hardware channels). Don't downgrade ASIL without a formal decomposition argument.

## Try It Yourself

1. Take a hazard from your own system (e.g., "unintended airbag deployment") and write the full decomposition chain: Safety Goal → FSR → TSR → SSR. Use the EARS notation for at least one SSR.

2. Implement a plausibility check function in C for your hazard. Include a lookup table, hysteresis, and a fault assertion. Ensure the function has a single responsibility and is traceable to your SSR.

3. Review your existing requirements for "and" statements. Find one requirement that contains two conditions and split it into two separate requirements, each with its own ID and traceability link.

## Next Up

Tomorrow: **Defensive Programming for Safety: MISRA & Coding Rules** — I'll dive into how coding standards like MISRA C:2023 enforce safety at the statement level, and show practical examples of rule violations that have caused real-world failures.
