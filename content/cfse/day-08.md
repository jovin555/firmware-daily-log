---
title: "Day 08: ASIL Decomposition: Splitting Safety Requirements"
date: 2026-06-22
tags: ["til", "cfse", "asil", "decomposition"]
---

## What I Explored Today

Today I dug into ASIL decomposition as defined in ISO 26262-9 (Clause 5). This is the technique that lets you take a single safety requirement assigned ASIL D and split it across two (or more) redundant elements, each carrying a lower ASIL. The goal is not to reduce the overall risk—the vehicle still needs ASIL D integrity—but to allow the design to use less costly components or simpler development processes on each path, provided the combination still meets the original target. I worked through a real example: decomposing an ASIL D brake-by-wire torque command into two independent channels, one at ASIL B and one at ASIL B(D). The notation matters, and so does the proof of independence.

## The Core Concept

Why decompose? Because ASIL D hardware is expensive. An ASIL D microcontroller might require lockstep cores, ECC on all memories, and a certified RTOS. If you can split the safety goal across two ASIL B microcontrollers, each can be a standard automotive-grade part with a simpler safety manual. The catch: the decomposition must be *proven independent*. If a common cause failure (e.g., a shared power supply glitch) can knock out both channels simultaneously, the decomposition is invalid. ISO 26262-9:2018 Clause 5.4.3 requires a *freedom-from-interference* argument between the decomposed elements. In practice, this means separate clock domains, separate power rails, separate memory, and often separate software stacks.

The ASIL after decomposition is written as `ASIL X(Y)` where `X` is the target ASIL of the decomposed element and `Y` is the original ASIL of the requirement. For example, `ASIL B(D)` means the element is developed to ASIL B processes, but it participates in an ASIL D decomposition. This notation is critical in safety manuals and work products.

## Key Commands / Configuration / Code

Here's a practical example using a simplified safety requirement in a requirements management tool (e.g., DOORS or Polarion). The key is to trace the decomposition in the safety case.

**1. Original Safety Requirement (before decomposition)**

```
ID: SAF-REQ-0421
Title: Brake torque command must be computed correctly
ASIL: D
Description: The brake torque request from the VCU to the brake actuator shall be computed with integrity sufficient to prevent unintended braking above 0.3g.
```

**2. Decomposed Safety Requirements**

```
ID: SAF-REQ-0421-A
Title: Primary brake torque computation (Channel 1)
ASIL: B(D)
Description: Channel 1 shall compute the brake torque request independently from Channel 2. 
             Shall meet ASIL B development processes.
             Redundant with SAF-REQ-0421-B.

ID: SAF-REQ-0421-B
Title: Secondary brake torque computation (Channel 2)
ASIL: B(D)
Description: Channel 2 shall compute the brake torque request independently from Channel 1.
             Shall meet ASIL B development processes.
             Redundant with SAF-REQ-0421-A.
```

**3. Independence Claim (in safety case, e.g., using GSN notation)**

```
Goal: G1 - Freedom from interference between Channel 1 and Channel 2
Evidence:
  - E1: Separate power supply domains (verified by schematic review)
  - E2: Separate clock sources (verified by clock tree analysis)
  - E3: No shared memory (verified by memory map review)
  - E4: Software runs on separate cores with independent stacks
```

**4. Example C code snippet for a voter (simplified)**

```c
// voter.c - Implements a simple comparator for decomposed channels
// ASIL B(D) development

#include <stdint.h>
#include <stdbool.h>

typedef struct {
    uint16_t torque_command;  // in Nm, scaled by 10
    uint8_t  crc;             // simple XOR checksum
} ChannelData;

// Returns true if both channels agree within tolerance
// Tolerance is 5% of full scale (e.g., 2000 Nm max -> 100 Nm)
bool compare_channels(ChannelData *ch1, ChannelData *ch2, uint16_t tolerance) {
    // Check CRC first (simple integrity check)
    uint8_t calc_crc1 = 0;
    uint8_t calc_crc2 = 0;
    uint8_t *data1 = (uint8_t*)ch1;
    uint8_t *data2 = (uint8_t*)ch2;
    
    for (int i = 0; i < sizeof(ChannelData) - 1; i++) {
        calc_crc1 ^= data1[i];
        calc_crc2 ^= data2[i];
    }
    
    if (calc_crc1 != ch1->crc || calc_crc2 != ch2->crc) {
        return false;  // CRC mismatch - data corruption
    }
    
    // Compare torque commands
    uint16_t diff = (ch1->torque_command > ch2->torque_command) ? 
                    (ch1->torque_command - ch2->torque_command) :
                    (ch2->torque_command - ch1->torque_command);
    
    return (diff <= tolerance);
}
```

**5. Safety Manual excerpt (for the voter component)**

```
Component: Voter_ASIL_B_D
ASIL Capability: B(D)
Safety Mechanism: Comparison of redundant channels with CRC check
Diagnostic Coverage: 99% (assumed for this example)
Fault Handling: If mismatch detected, set torque to 0 (safe state)
```

## Common Pitfalls & Gotchas

1. **Assuming decomposition reduces the overall ASIL.** It does not. The vehicle-level hazard still requires ASIL D. Decomposition only changes the *allocation* of requirements to elements. You must still prove that the combination of the two ASIL B elements is equivalent to a single ASIL D element. This is a common misunderstanding in safety reviews.

2. **Ignoring common cause failures (CCFs).** If both channels share a voltage regulator, a single regulator failure can disable both. The decomposition is invalid. ISO 26262-9:2018 Clause 5.4.4 requires a CCF analysis (e.g., using a checklist from Part 9, Annex D). I've seen projects fail audits because they forgot to check for shared interrupts or shared DMA channels.

3. **Mislabeling ASIL in the safety manual.** Writing `ASIL B` instead of `ASIL B(D)` is a documentation error that can cause a non-conformance. The `(D)` suffix is not optional—it signals that this element is part of a decomposition. Without it, a reviewer might assume the element is standalone ASIL B, which changes the safety case assumptions.

## Try It Yourself

1. **Decompose an ASIL D requirement** for a steering angle sensor. Write two decomposed requirements (ASIL C(D) each) and list three independence claims (e.g., separate power, separate communication bus, separate clock).

2. **Perform a CCF analysis** on a hypothetical dual-channel design: two microcontrollers sharing a single 5V regulator and a single CAN bus transceiver. Identify at least two common cause failures that would invalidate the decomposition.

3. **Write a voter function** in C that compares two redundant sensor readings (e.g., wheel speed) and outputs the average if within 2% tolerance, or sets a fault flag otherwise. Add a CRC check on each channel's data structure.

## Next Up

Tomorrow: ISO 26262 Part 6 — Product Development at the Software Level. We'll cover software unit design, static code analysis, and how to map ASIL requirements to coding standards like MISRA C:2023.
